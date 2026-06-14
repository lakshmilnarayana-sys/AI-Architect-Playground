from __future__ import annotations

from pathlib import Path

import typer

from perfagent.core.artifacts import read_json
from perfagent.config import load_run_config, resolve_evaluate_options
from perfagent.collectors.prometheus_collector import load_prometheus_query_config, validate_prometheus_queries
from perfagent.collectors.distributed_results import write_merged_worker_results
from perfagent.collectors.profiling_collector import build_profile_capture_plan, execute_profile_capture_plan
from perfagent.collectors.observability_adapters import validate_provider_query_pack
from perfagent.core.artifacts import write_json
from perfagent.analyzers.similar_regressions import find_similar_regressions
from perfagent.executors.capacity_search import run_capacity_search
from perfagent.executors.distributed import build_distributed_coordinator_plan, build_distributed_plan, run_distributed_coordinator
from perfagent.generators.trend_dashboard import render_trend_dashboard
from perfagent.mcp_server import serve_stdio
from perfagent.storage.vector_store import PgVectorStore, chunk_text
from perfagent.storage.run_store import RunStore, compare_to_latest_baseline
from perfagent.workflow import evaluate_service, generate_only, import_external_results
from perfagent.ci.pr_comment import format_pr_comment


app = typer.Typer(help="PerfAgent AI: from API contract to performance report.")
prometheus_app = typer.Typer(help="Prometheus helpers.")
baseline_app = typer.Typer(help="Baseline management.")
storage_app = typer.Typer(help="Run database management.")
regression_app = typer.Typer(help="Regression comparison gates.")
distributed_app = typer.Typer(help="Distributed/container execution planning.")
capacity_app = typer.Typer(help="Capacity search execution.")
profile_app = typer.Typer(help="Profiling and flamegraph helpers.")
observability_app = typer.Typer(help="Observability provider helpers.")
ci_app = typer.Typer(help="CI helper commands.")
app.add_typer(prometheus_app, name="prometheus")
app.add_typer(baseline_app, name="baseline")
app.add_typer(storage_app, name="storage")
app.add_typer(regression_app, name="regression")
app.add_typer(distributed_app, name="distributed")
app.add_typer(capacity_app, name="capacity")
app.add_typer(profile_app, name="profile")
app.add_typer(observability_app, name="observability")
app.add_typer(ci_app, name="ci")


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
    capacity_probe_rps: int | None = typer.Option(None, "--capacity-probe-rps", help="Single target RPS for capacity probe mode."),
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
    profile_auto: bool | None = typer.Option(None, "--profile-auto/--no-profile-auto", help="Run supported profiler capture commands during execution."),
    profile_mode: str | None = typer.Option(None, "--profile-mode", help="Profiling mode: ebpf, runtime, or auto."),
    profile_pid: str | None = typer.Option(None, "--profile-pid"),
    profile_endpoint: str | None = typer.Option(None, "--profile-endpoint"),
    profile_container: str | None = typer.Option(None, "--profile-container"),
    workflow_engine: str = typer.Option("deterministic", "--workflow", help="Workflow engine: deterministic or langgraph."),
    store: bool = typer.Option(True, "--store/--no-store", help="Persist run metadata to the configured run store."),
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
            "capacity_probe_rps": capacity_probe_rps,
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
            "profile_auto": profile_auto,
            "profile_mode": profile_mode,
            "profile_pid": profile_pid,
            "profile_endpoint": profile_endpoint,
            "profile_container": profile_container,
        },
    )
    missing = [key for key in ["service_name", "openapi_path", "target_url", "runtime", "slo_p95_ms", "slo_error_rate_percent", "output_dir"] if options.get(key) is None]
    if missing:
        raise typer.BadParameter(f"Missing required evaluate options: {', '.join(missing)}")
    if not store:
        options["storage"] = {"enabled": False}
    typer.echo("Creating evaluation run...")
    evaluate_kwargs = {
        "service_name": options["service_name"],
        "openapi_path": Path(options["openapi_path"]),
        "target_url": options["target_url"],
        "runtime": options["runtime"],
        "slo_p95_ms": int(options["slo_p95_ms"]),
        "slo_error_rate_percent": float(options["slo_error_rate_percent"]),
        "duration": options["duration"],
        "output_dir": Path(options["output_dir"]),
        "engine": options["engine"],
        "mode": options["mode"],
        "capacity_probe_rps": options.get("capacity_probe_rps"),
        "service_resources": options.get("service_resources"),
        "dependencies": options.get("dependencies", []),
        "llm": options.get("llm"),
        "traffic_profile_config": options.get("traffic_profile"),
        "observability_config": options.get("observability"),
        "protocol_config": options.get("protocols"),
        "profiling_config": options.get("profiling"),
        "storage": options.get("storage"),
        "prometheus_url": options.get("prometheus_url"),
        "prometheus_service_label": options.get("prometheus_service_label"),
        "prometheus_query_config_path": Path(options["prometheus_query_config_path"]) if options.get("prometheus_query_config_path") else None,
        "profile_paths": profile,
        "skip_run": skip_run,
    }
    if workflow_engine.lower() == "langgraph":
        from perfagent.workflow_graph import run_langgraph_evaluation

        state = run_langgraph_evaluation(**evaluate_kwargs)
    elif workflow_engine.lower() == "deterministic":
        state = evaluate_service(**evaluate_kwargs)
    else:
        raise typer.BadParameter("--workflow must be deterministic or langgraph")
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


@capacity_app.command("search")
def capacity_search(
    service_name: str = typer.Option(..., "--service-name"),
    openapi: Path = typer.Option(..., "--openapi", exists=True, readable=True),
    target_url: str = typer.Option(..., "--target-url"),
    runtime: str = typer.Option(..., "--runtime"),
    slo_p95_ms: int = typer.Option(..., "--slo-p95-ms"),
    slo_error_rate: float = typer.Option(..., "--slo-error-rate"),
    duration: str = typer.Option("1m", "--duration"),
    output: Path = typer.Option(Path("./outputs/capacity-search"), "--output"),
    engine: str = typer.Option("k6", "--engine"),
    min_rps: int = typer.Option(50, "--min-rps"),
    max_rps: int = typer.Option(800, "--max-rps"),
    steps: int = typer.Option(6, "--steps"),
    repeats: int = typer.Option(1, "--repeats"),
    refinement_steps: int = typer.Option(0, "--refinement-steps"),
    fail_fast: bool = typer.Option(True, "--fail-fast/--no-fail-fast"),
    output_json: Path | None = typer.Option(None, "--output-json"),
) -> None:
    result = run_capacity_search(
        service_name=service_name,
        openapi_path=openapi,
        target_url=target_url,
        runtime=runtime,
        slo_p95_ms=slo_p95_ms,
        slo_error_rate_percent=slo_error_rate,
        duration=duration,
        output_dir=output,
        engine=engine,
        min_rps=min_rps,
        max_rps=max_rps,
        steps=steps,
        repeats=repeats,
        refinement_steps=refinement_steps,
        fail_fast=fail_fast,
    )
    if output_json:
        write_json(output_json, result)
    typer.echo(f"Capacity search completed: {output / 'capacity_search.json'}")
    typer.echo(f"Estimated capacity RPS: {result['estimated_capacity_rps']}")
    typer.echo(f"Breaking point RPS: {result['breaking_point_rps']}")


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


@distributed_app.command("merge")
def distributed_merge(
    worker_summary: list[Path] = typer.Option(..., "--worker-summary", exists=True, readable=True),
    output_dir: Path = typer.Option(Path("./outputs/distributed-merged"), "--output-dir"),
) -> None:
    result = write_merged_worker_results(
        worker_summary,
        summary_path=output_dir / "raw" / "merged_summary.json",
        aligned_path=output_dir / "processed" / "aligned_timeseries.csv",
    )
    typer.echo(f"Merged {result['workers']} worker summaries.")
    typer.echo(f"Summary: {result['summary_path']}")
    typer.echo(f"Aligned time-series: {result['aligned_path']}")


@distributed_app.command("coordinate")
def distributed_coordinate(
    service_name: str = typer.Option(..., "--service-name"),
    engine: str = typer.Option("k6", "--engine"),
    workers: int = typer.Option(2, "--workers"),
    output: Path = typer.Option(Path("./outputs/distributed-coordinator-plan.json"), "--output"),
    base_config: str = typer.Option("./examples/sample-config.yaml", "--config"),
    compose_service: str = typer.Option("perfagent", "--compose-service"),
    execute: bool = typer.Option(False, "--execute", help="Execute worker commands and merge available results."),
) -> None:
    plan = build_distributed_coordinator_plan(
        engine=engine,
        service_name=service_name,
        workers=workers,
        output_dir=output.parent,
        base_config=base_config,
        compose_service=compose_service,
    )
    if execute:
        result = run_distributed_coordinator(plan, output_path=output)
        typer.echo(f"Distributed coordinator executed: {output}")
        typer.echo(f"Workers: {len(result['workers'])}")
        typer.echo(f"Success: {result['success']}")
        if not result["success"]:
            raise typer.Exit(2)
        return
    write_json(output, plan)
    typer.echo(f"Distributed coordinator plan: {output}")
    for worker in plan["worker_specs"]:
        typer.echo(worker["command"])
    typer.echo(plan["merge_command"])


@distributed_app.command("run")
def distributed_run(
    service_name: str = typer.Option(..., "--service-name"),
    engine: str = typer.Option("k6", "--engine"),
    workers: int = typer.Option(2, "--workers"),
    output: Path = typer.Option(Path("./outputs/distributed-run.json"), "--output"),
    base_config: str = typer.Option("./examples/sample-config.yaml", "--config"),
    compose_service: str = typer.Option("perfagent", "--compose-service"),
) -> None:
    plan = build_distributed_coordinator_plan(
        engine=engine,
        service_name=service_name,
        workers=workers,
        output_dir=output.parent,
        base_config=base_config,
        compose_service=compose_service,
    )
    result = run_distributed_coordinator(plan, output_path=output)
    typer.echo(f"Distributed run result: {output}")
    typer.echo(f"Workers: {len(result['workers'])}")
    typer.echo(f"Merged: {bool(result['merged'])}")
    if not result["success"]:
        raise typer.Exit(2)


@profile_app.command("plan")
def profile_plan(
    runtime: str = typer.Option(..., "--runtime"),
    mode: str = typer.Option("ebpf", "--mode", help="Profiling mode: ebpf, runtime, or auto."),
    output_dir: Path = typer.Option(Path("./outputs/profiles"), "--output-dir"),
    duration_seconds: int = typer.Option(60, "--duration-seconds"),
    pid: str | None = typer.Option(None, "--pid"),
    profile_endpoint: str | None = typer.Option(None, "--profile-endpoint"),
    container: str | None = typer.Option(None, "--container"),
    output_json: Path | None = typer.Option(None, "--output-json"),
) -> None:
    plan = build_profile_capture_plan(
        runtime=runtime,
        output_dir=output_dir,
        duration_seconds=duration_seconds,
        pid=pid,
        profile_endpoint=profile_endpoint,
        container=container,
        mode=mode,
    )
    if output_json:
        write_json(output_json, plan)
    typer.echo(f"Profiling plan for {runtime}")
    for command in plan["commands"]:
        status = "available" if command["available"] else "missing"
        typer.echo(f"- [{status}] {command['command']}")
    for warning in plan["warnings"]:
        typer.echo(f"WARNING: {warning}")


@profile_app.command("run")
def profile_run(
    runtime: str = typer.Option(..., "--runtime"),
    mode: str = typer.Option("ebpf", "--mode", help="Profiling mode: ebpf, runtime, or auto."),
    output_dir: Path = typer.Option(Path("./outputs/profiles"), "--output-dir"),
    duration_seconds: int = typer.Option(60, "--duration-seconds"),
    pid: str | None = typer.Option(None, "--pid"),
    profile_endpoint: str | None = typer.Option(None, "--profile-endpoint"),
    container: str | None = typer.Option(None, "--container"),
    output_json: Path | None = typer.Option(None, "--output-json"),
) -> None:
    plan = build_profile_capture_plan(
        runtime=runtime,
        output_dir=output_dir / "captured",
        duration_seconds=duration_seconds,
        pid=pid,
        profile_endpoint=profile_endpoint,
        container=container,
        mode=mode,
    )
    result = execute_profile_capture_plan(plan, log_dir=output_dir / "logs", timeout_seconds=duration_seconds + 30)
    if output_json:
        write_json(output_json, result)
    typer.echo(f"Profiler capture completed: {output_json or output_dir}")
    typer.echo(f"Started commands: {result['started_count']}")
    for warning in result.get("warnings", []):
        typer.echo(f"WARNING: {warning}")


@observability_app.command("query-pack")
def observability_query_pack(
    provider: str = typer.Option(..., "--provider"),
    service_name: str = typer.Option(..., "--service-name"),
    output_json: Path | None = typer.Option(None, "--output-json"),
    api_key: str | None = typer.Option(None, "--api-key"),
    app_key: str | None = typer.Option(None, "--app-key"),
    account_id: str | None = typer.Option(None, "--account-id"),
    site: str | None = typer.Option(None, "--site"),
    base_url: str | None = typer.Option(None, "--base-url"),
    index: str | None = typer.Option(None, "--index"),
) -> None:
    result = validate_provider_query_pack(
        provider,
        service_name,
        {
            "api_key": api_key,
            "app_key": app_key,
            "account_id": account_id,
            "site": site,
            "base_url": base_url,
            "index": index,
        },
    )
    if output_json:
        write_json(output_json, result)
    typer.echo(f"Observability query pack: {result['provider']}")
    typer.echo(f"Valid: {result['valid']}")
    for name, query in result.get("queries", {}).items():
        typer.echo(f"{name}: {query}")
    for warning in result.get("warnings", []):
        typer.echo(f"WARNING: {warning}")


@ci_app.command("comment")
def ci_comment(
    summary: Path = typer.Option(..., "--summary", exists=True, readable=True),
    regression: Path | None = typer.Option(None, "--regression", exists=True, readable=True),
    output: Path | None = typer.Option(None, "--output"),
) -> None:
    markdown = format_pr_comment(
        read_json(summary),
        read_json(regression) if regression else None,
    )
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(markdown)
        typer.echo(f"PR comment markdown: {output}")
    else:
        typer.echo(markdown)


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
    dsn: str | None = typer.Option(None, "--postgres-dsn"),
    db_path: Path = typer.Option(Path("./outputs/perfagent.db"), "--db-path"),
    service_name: str | None = typer.Option(None, "--service-name"),
    limit: int = typer.Option(5, "--limit"),
    output_json: Path | None = typer.Option(None, "--output-json"),
) -> None:
    vector_matches = PgVectorStore(dsn).similar(query, limit=limit) if dsn else []
    result = find_similar_regressions(
        query=query,
        runs=RunStore(db_path).list_runs(service_name),
        vector_matches=vector_matches,
        service_name=service_name,
        limit=limit,
    )
    if output_json:
        write_json(output_json, result)
    typer.echo(result["summary"])
    for item in result["sql_candidates"]:
        typer.echo(
            f"SQL {item['run_id']} {item['release_decision']} "
            f"p95={item['max_p95_latency_ms']} error={item['max_error_rate_percent']} breakpoint={item['breaking_point_rps']}"
        )
    for item in result["vector_matches"]:
        typer.echo(f"VECTOR {item['run_id']} {item['chunk_type']}#{item['chunk_index']} distance={item['distance']}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
