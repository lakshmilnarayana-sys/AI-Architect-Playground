from __future__ import annotations

from pathlib import Path

import typer

from perfagent.core.artifacts import read_json
from perfagent.config import load_run_config, resolve_evaluate_options
from perfagent.collectors.prometheus_collector import load_prometheus_query_config, validate_prometheus_queries
from perfagent.core.artifacts import write_json
from perfagent.executors.distributed import build_distributed_plan
from perfagent.generators.trend_dashboard import render_trend_dashboard
from perfagent.mcp_server import serve_stdio
from perfagent.storage.vector_store import PgVectorStore, chunk_text
from perfagent.storage.run_store import RunStore, compare_to_latest_baseline
from perfagent.workflow import evaluate_service, generate_only, import_external_results


app = typer.Typer(help="PerfAgent AI: from API contract to performance report.")
prometheus_app = typer.Typer(help="Prometheus helpers.")
baseline_app = typer.Typer(help="Baseline management.")
storage_app = typer.Typer(help="Run database management.")
regression_app = typer.Typer(help="Regression comparison gates.")
distributed_app = typer.Typer(help="Distributed/container execution planning.")
app.add_typer(prometheus_app, name="prometheus")
app.add_typer(baseline_app, name="baseline")
app.add_typer(storage_app, name="storage")
app.add_typer(regression_app, name="regression")
app.add_typer(distributed_app, name="distributed")


@app.command()
def evaluate(
    config: Path | None = typer.Option(None, "--config", exists=True, readable=True),
    service_name: str | None = typer.Option(None, "--service-name"),
    openapi: Path | None = typer.Option(None, "--openapi", exists=True, readable=True),
    target_url: str | None = typer.Option(None, "--target-url"),
    runtime: str | None = typer.Option(None, "--runtime"),
    slo_p95_ms: int | None = typer.Option(None, "--slo-p95-ms"),
    slo_error_rate: float | None = typer.Option(None, "--slo-error-rate"),
    duration: str | None = typer.Option(None, "--duration"),
    output: Path | None = typer.Option(None, "--output"),
    engine: str | None = typer.Option(None, "--engine", help="Execution engine: k6, locust, jmeter, grpc, websocket, ui, browser."),
    mode: str | None = typer.Option(None, "--mode", help="Evaluation mode: standard or capacity."),
    cpu_allocation: str | None = typer.Option(None, "--service-cpu", help="Service CPU allocation, for example 500m or 2 cores."),
    memory_allocation: str | None = typer.Option(None, "--service-memory", help="Service memory allocation, for example 512Mi."),
    disk_allocation: str | None = typer.Option(None, "--service-disk", help="Service disk allocation, for example 2Gi."),
    image_tag: str | None = typer.Option(None, "--service-image-tag", help="Container image tag under test."),
    llm_provider: str | None = typer.Option(None, "--llm-provider", help="LLM provider. Supported: ollama."),
    llm_model: str | None = typer.Option(None, "--llm-model", help="LLM model name, for example llama3.2."),
    llm_base_url: str | None = typer.Option(None, "--llm-base-url", help="Ollama base URL."),
    traffic_profile: str | None = typer.Option(None, "--traffic-profile", help="Traffic profile mode. Use 'production' to derive load from observability."),
    prometheus_url: str | None = typer.Option(None, "--prometheus-url"),
    prometheus_service_label: str | None = typer.Option(None, "--prometheus-service-label"),
    prometheus_query_config: Path | None = typer.Option(
        None,
        "--prometheus-query-config",
        exists=True,
        readable=True,
        help="YAML/JSON file containing custom PromQL query templates.",
    ),
    profile: list[Path] | None = typer.Option(None, "--profile", help="Path to an existing profiling artifact to attach."),
    skip_run: bool = typer.Option(False, "--skip-run"),
    fail_on: str = typer.Option("", "--fail-on", help="Comma-separated release decisions that should fail the command."),
) -> None:
    options = resolve_evaluate_options(
        load_run_config(config),
        {
            "service_name": service_name,
            "openapi_path": str(openapi) if openapi else None,
            "target_url": target_url,
            "runtime": runtime,
            "slo_p95_ms": slo_p95_ms,
            "slo_error_rate_percent": slo_error_rate,
            "duration": duration,
            "output_dir": str(output) if output else None,
            "engine": engine,
            "mode": mode,
            "cpu_allocation": cpu_allocation,
            "memory_allocation": memory_allocation,
            "disk_allocation": disk_allocation,
            "image_tag": image_tag,
            "llm_enabled": True if llm_provider else None,
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "llm_base_url": llm_base_url,
            "traffic_profile_mode": traffic_profile,
            "prometheus_url": prometheus_url,
            "prometheus_service_label": prometheus_service_label,
            "prometheus_query_config_path": str(prometheus_query_config) if prometheus_query_config else None,
        },
    )
    missing = [key for key in ["service_name", "openapi_path", "target_url", "runtime", "slo_p95_ms", "slo_error_rate_percent", "output_dir"] if options.get(key) is None]
    if missing:
        raise typer.BadParameter(f"Missing required evaluate options: {', '.join(missing)}")
    typer.echo("Creating evaluation run...")
    state = evaluate_service(
        service_name=options["service_name"],
        openapi_path=Path(options["openapi_path"]),
        target_url=options["target_url"],
        runtime=options["runtime"],
        slo_p95_ms=int(options["slo_p95_ms"]),
        slo_error_rate_percent=float(options["slo_error_rate_percent"]),
        duration=options["duration"],
        output_dir=Path(options["output_dir"]),
        engine=options["engine"],
        mode=options["mode"],
        service_resources=options.get("service_resources"),
        dependencies=options.get("dependencies", []),
        llm=options.get("llm"),
        traffic_profile_config=options.get("traffic_profile"),
        observability_config=options.get("observability"),
        protocol_config=options.get("protocols"),
        storage=options.get("storage"),
        prometheus_url=options.get("prometheus_url"),
        prometheus_service_label=options.get("prometheus_service_label"),
        prometheus_query_config_path=Path(options["prometheus_query_config_path"]) if options.get("prometheus_query_config_path") else None,
        profile_paths=profile,
        skip_run=skip_run,
    )
    typer.echo("Run completed.")
    typer.echo(f"Release decision: {state['release_decision']}")
    typer.echo(f"Stable RPS: {state['features'].get('stable_rps', 0)}")
    typer.echo(f"Max p95 latency: {state['features'].get('max_p95_latency_ms', 0)} ms")
    typer.echo(f"Max error rate: {state['features'].get('max_error_rate_percent', 0)}%")
    typer.echo("Report:")
    typer.echo(state["report_html_path"])
    fail_decisions = {item.strip().upper() for item in fail_on.split(",") if item.strip()}
    if state["release_decision"].upper() in fail_decisions:
        typer.echo(f"Performance gate failed: {state['release_decision']}", err=True)
        raise typer.Exit(2)


@app.command()
def generate(
    service_name: str = typer.Option(..., "--service-name"),
    openapi: Path = typer.Option(..., "--openapi", exists=True, readable=True),
    target_url: str = typer.Option(..., "--target-url"),
    output: Path = typer.Option(..., "--output"),
) -> None:
    artifacts = generate_only(
        service_name=service_name,
        openapi_path=openapi,
        target_url=target_url,
        output_dir=output,
    )
    typer.echo(f"Generated k6 script: {artifacts['k6_script']}")


@app.command()
def analyze(run_dir: Path = typer.Option(..., "--run-dir", exists=True, file_okay=False)) -> None:
    summary_path = run_dir / "reports" / "summary.json"
    if not summary_path.exists():
        raise typer.BadParameter(f"Missing summary artifact: {summary_path}")
    summary = read_json(summary_path)
    typer.echo(f"Release decision: {summary.get('release_decision', 'UNKNOWN')}")
    typer.echo(f"Bottleneck: {summary.get('bottleneck_analysis', {}).get('bottleneck', 'unknown')}")


@app.command("import-results")
def import_results(
    run_dir: Path = typer.Option(..., "--run-dir", file_okay=False),
    tool: str = typer.Option(..., "--tool", help="External tool name: locust or jmeter."),
    result_path: Path = typer.Option(..., "--result", exists=True, readable=True),
    service_name: str = typer.Option(..., "--service-name"),
    runtime: str = typer.Option(..., "--runtime"),
    target_url: str = typer.Option(..., "--target-url"),
    slo_p95_ms: int = typer.Option(..., "--slo-p95-ms"),
    slo_error_rate: float = typer.Option(..., "--slo-error-rate"),
    cpu_allocation: str | None = typer.Option(None, "--service-cpu"),
    memory_allocation: str | None = typer.Option(None, "--service-memory"),
    disk_allocation: str | None = typer.Option(None, "--service-disk"),
    image_tag: str | None = typer.Option(None, "--service-image-tag"),
) -> None:
    result = import_external_results(
        run_dir=run_dir,
        tool=tool,
        result_path=result_path,
        service_name=service_name,
        runtime=runtime,
        target_url=target_url,
        slo_p95_ms=slo_p95_ms,
        slo_error_rate_percent=slo_error_rate,
        service_resources={
            "cpu_allocation": cpu_allocation,
            "memory_allocation": memory_allocation,
            "disk_allocation": disk_allocation,
            "image_tag": image_tag,
        },
    )
    typer.echo(f"Imported {result['tool']} results.")
    typer.echo(f"Release decision: {result['features'].get('release_decision', 'UNKNOWN')}")
    typer.echo("Report:")
    typer.echo(result["report_html_path"])


@app.command("mcp")
def mcp() -> None:
    serve_stdio()


@prometheus_app.command("validate")
def prometheus_validate(
    prometheus_url: str = typer.Option(..., "--prometheus-url"),
    prometheus_service_label: str | None = typer.Option(None, "--prometheus-service-label"),
    prometheus_query_config: Path | None = typer.Option(None, "--prometheus-query-config", exists=True, readable=True),
) -> None:
    result = validate_prometheus_queries(
        prometheus_url,
        prometheus_service_label,
        query_templates=load_prometheus_query_config(prometheus_query_config),
    )
    typer.echo(f"Prometheus validation: {result['status']}")
    for name, item in result["results"].items():
        status = "OK" if item["available"] else "MISSING"
        detail = f" ({item['error']})" if item.get("error") else ""
        typer.echo(f"{name}: {status}, samples={item['sample_count']}{detail}")
    if result["status"] != "passed":
        raise typer.Exit(2)


@baseline_app.command("save")
def baseline_save(
    run_dir: Path = typer.Option(..., "--run-dir", exists=True, file_okay=False),
    baseline_dir: Path = typer.Option(Path("./baselines"), "--baseline-dir"),
) -> None:
    summary = read_json(run_dir / "reports" / "summary.json")
    service_name = summary.get("service_name", "service")
    baseline_dir.mkdir(parents=True, exist_ok=True)
    destination = baseline_dir / f"{service_name}.json"
    write_json(destination, summary)
    typer.echo(f"Saved baseline: {destination}")


@baseline_app.command("compare")
def baseline_compare(
    run_dir: Path = typer.Option(..., "--run-dir", exists=True, file_okay=False),
    baseline_dir: Path = typer.Option(Path("./baselines"), "--baseline-dir"),
) -> None:
    current = read_json(run_dir / "reports" / "summary.json")
    service_name = current.get("service_name", "service")
    baseline = read_json(baseline_dir / f"{service_name}.json")
    current_features = current.get("features", {})
    baseline_features = baseline.get("features", {})
    p95_delta = float(current_features.get("max_p95_latency_ms", 0)) - float(
        baseline_features.get("max_p95_latency_ms", 0)
    )
    rps_delta = float(current_features.get("stable_rps", 0)) - float(baseline_features.get("stable_rps", 0))
    error_delta = float(current_features.get("max_error_rate_percent", 0)) - float(
        baseline_features.get("max_error_rate_percent", 0)
    )
    typer.echo(f"Baseline comparison for {service_name}")
    typer.echo(f"p95 latency delta: {p95_delta}")
    typer.echo(f"stable RPS delta: {rps_delta}")
    typer.echo(f"error rate delta: {error_delta}")


@storage_app.command("list")
def storage_list(
    db_path: Path = typer.Option(Path("./outputs/perfagent.db"), "--db-path"),
    service_name: str | None = typer.Option(None, "--service-name"),
) -> None:
    store = RunStore(db_path)
    for run in store.list_runs(service_name):
        typer.echo(
            f"{run['created_at']} {run['service_name']} {run['run_id']} "
            f"{run['release_decision']} p95={run['max_p95_latency_ms']} rps={run['stable_rps']}"
        )


@storage_app.command("retention")
def storage_retention(
    db_path: Path = typer.Option(Path("./outputs/perfagent.db"), "--db-path"),
    retention_days: int = typer.Option(30, "--retention-days"),
) -> None:
    deleted = RunStore(db_path).apply_retention(retention_days=retention_days)
    typer.echo(f"Deleted {deleted} runs older than {retention_days} days")


@storage_app.command("dashboard")
def storage_dashboard(
    db_path: Path = typer.Option(Path("./outputs/perfagent.db"), "--db-path"),
    output: Path = typer.Option(Path("./outputs/trends.html"), "--output"),
    service_name: str | None = typer.Option(None, "--service-name"),
) -> None:
    path = render_trend_dashboard(RunStore(db_path).list_runs(service_name), output)
    typer.echo(f"Trend dashboard: {path}")


@distributed_app.command("plan")
def distributed_plan(
    service_name: str = typer.Option(..., "--service-name"),
    engine: str = typer.Option("k6", "--engine"),
    workers: int = typer.Option(2, "--workers"),
    output: Path = typer.Option(Path("./outputs/distributed-plan.json"), "--output"),
    compose_service: str = typer.Option("perfagent", "--compose-service"),
) -> None:
    plan = build_distributed_plan(
        engine=engine,
        service_name=service_name,
        workers=workers,
        output_dir=output.parent,
        compose_service=compose_service,
    )
    write_json(output, plan)
    typer.echo(f"Distributed plan: {output}")
    for command in plan["commands"]:
        typer.echo(command)


@regression_app.command("compare")
def regression_compare(
    run_dir: Path = typer.Option(..., "--run-dir", exists=True, file_okay=False),
    db_path: Path = typer.Option(Path("./outputs/perfagent.db"), "--db-path"),
    max_p95_regression_percent: float = typer.Option(20.0, "--max-p95-regression-percent"),
    max_error_rate_delta_percent: float = typer.Option(0.5, "--max-error-rate-delta-percent"),
    output_json: Path | None = typer.Option(None, "--output-json"),
    fail_on_regression: bool = typer.Option(False, "--fail-on-regression"),
) -> None:
    summary = read_json(run_dir / "reports" / "summary.json")
    service_name = summary.get("service_name")
    if not service_name:
        raise typer.BadParameter("summary.json is missing service_name")
    result = compare_to_latest_baseline(
        RunStore(db_path),
        service_name,
        summary.get("features", {}),
        exclude_run_id=summary.get("run_id"),
        max_p95_regression_percent=max_p95_regression_percent,
        max_error_rate_delta_percent=max_error_rate_delta_percent,
    )
    if output_json:
        write_json(output_json, result)
    typer.echo(f"Regression comparison for {service_name}")
    typer.echo(f"Baseline run: {result.get('baseline_run_id') or 'none'}")
    typer.echo(f"Regression detected: {result['regression_detected']}")
    for finding in result.get("findings", []):
        typer.echo(f"- {finding}")
    if fail_on_regression and result["regression_detected"]:
        raise typer.Exit(2)


@regression_app.command("index")
def regression_index(
    run_dir: Path = typer.Option(..., "--run-dir", exists=True, file_okay=False),
    dsn: str = typer.Option(..., "--postgres-dsn"),
) -> None:
    summary_path = run_dir / "reports" / "summary.json"
    report_path = run_dir / "reports" / "report.md"
    summary = read_json(summary_path)
    text = report_path.read_text() if report_path.exists() else summary_path.read_text()
    count = PgVectorStore(dsn).upsert_chunks(
        run_id=summary.get("run_id", run_dir.name),
        chunk_type="report",
        chunks=chunk_text(text),
    )
    typer.echo(f"Indexed {count} chunks for {summary.get('service_name', run_dir.name)}")


@regression_app.command("similar")
def regression_similar(
    query: str = typer.Option(..., "--query"),
    dsn: str = typer.Option(..., "--postgres-dsn"),
    limit: int = typer.Option(5, "--limit"),
) -> None:
    for item in PgVectorStore(dsn).similar(query, limit=limit):
        typer.echo(f"{item['run_id']} {item['chunk_type']}#{item['chunk_index']} distance={item['distance']}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
