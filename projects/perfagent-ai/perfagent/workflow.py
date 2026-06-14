from __future__ import annotations

from pathlib import Path
from typing import Any

from perfagent.analyzers.alignment import align_k6_jsonl, fallback_aligned_timeseries, write_aligned_csv
from perfagent.analyzers.bottlenecks import classify_bottleneck
from perfagent.analyzers.dependencies import analyze_dependencies
from perfagent.analyzers.features import extract_features
from perfagent.collectors.external_results import load_external_results
from perfagent.collectors.k6_collector import read_k6_summary, run_k6
from perfagent.collectors.profiling_collector import collect_profiling_artifacts
from perfagent.collectors.prometheus_collector import (
    collect_dependency_metrics,
    collect_prometheus_metrics,
    load_prometheus_query_config,
    merge_dependency_metrics,
    merge_prometheus_metrics,
)
from perfagent.config import default_strategy
from perfagent.core.artifacts import read_json, write_json, write_yaml
from perfagent.core.state import EvaluationState, initial_state
from perfagent.core.workspace import Workspace
from perfagent.generators.k6_generator import generate_k6_script
from perfagent.generators.grpc_generator import generate_grpc_load_test
from perfagent.generators.jmeter_generator import generate_jmeter_plan
from perfagent.generators.locust_generator import generate_locustfile
from perfagent.generators.report_renderer import render_reports
from perfagent.generators.synthetic_data import generate_test_data
from perfagent.generators.websocket_generator import generate_websocket_load_test
from perfagent.parsers.openapi_parser import parse_openapi


def evaluate_service(
    *,
    service_name: str,
    openapi_path: Path,
    target_url: str,
    runtime: str,
    slo_p95_ms: int,
    slo_error_rate_percent: float,
    duration: str,
    output_dir: Path,
    engine: str = "k6",
    mode: str = "standard",
    service_resources: dict[str, Any] | None = None,
    dependencies: list[dict[str, Any]] | None = None,
    prometheus_url: str | None = None,
    prometheus_service_label: str | None = None,
    prometheus_query_config_path: Path | None = None,
    profile_paths: list[Path] | None = None,
    skip_run: bool = False,
) -> EvaluationState:
    state = initial_state(
        service_name=service_name,
        openapi_path=str(openapi_path),
        target_url=target_url,
        runtime=runtime,
        output_dir=str(output_dir),
        slo_p95_ms=slo_p95_ms,
        slo_error_rate_percent=slo_error_rate_percent,
        duration=duration,
        engine=engine,
        mode=mode,
        prometheus_url=prometheus_url,
        prometheus_service_label=prometheus_service_label,
        prometheus_query_config_path=str(prometheus_query_config_path) if prometheus_query_config_path else None,
        service_resources=service_resources,
        dependencies=dependencies,
    )
    workspace = Workspace(output_dir)
    workspace.create()
    copied_openapi = workspace.copy_openapi(openapi_path)
    state["openapi_path"] = str(copied_openapi)

    contract = parse_openapi(copied_openapi, service_name)
    state["contract_analysis"] = contract
    write_json(workspace.processed_dir / "contract_analysis.json", contract)

    strategy = default_strategy(duration, slo_p95_ms, slo_error_rate_percent, mode=mode)
    state["test_strategy"] = strategy
    write_yaml(workspace.processed_dir / "test_strategy.yaml", strategy)
    write_yaml(workspace.processed_dir / "metric_contract.yaml", _metric_contract(state, strategy))

    test_data = generate_test_data(contract)
    state["test_data"] = test_data
    write_json(workspace.generated_dir / "test_data.json", test_data)

    script_path = generate_k6_script(
        contract,
        test_data,
        strategy,
        target_url,
        workspace.generated_dir / "perf_test.js",
    )
    state["generated_k6_script_path"] = str(script_path)
    generate_locustfile(contract, test_data, target_url, workspace.generated_dir / "locustfile.py")
    generate_jmeter_plan(contract, test_data, strategy, target_url, workspace.generated_dir / "jmeter_test_plan.jmx")
    generate_grpc_load_test(
        service_name=service_name,
        target=target_url.replace("http://", "").replace("https://", ""),
        proto_path="./protos/service.proto",
        output_path=workspace.generated_dir / "grpc_load.py",
    )
    generate_websocket_load_test(
        service_name=service_name,
        target_url=target_url.replace("http://", "ws://").replace("https://", "wss://"),
        output_path=workspace.generated_dir / "websocket_load.py",
    )

    summary_path = workspace.raw_dir / "k6_summary.json"
    timeseries_path = workspace.raw_dir / "k6_timeseries.jsonl"
    if skip_run or engine.lower() != "k6":
        execution_result: dict[str, Any] = {
            "exit_code": 0,
            "skipped": True,
            "summary_path": str(summary_path),
            "timeseries_path": str(timeseries_path),
            "stdout": "",
            "stderr": f"{engine} execution skipped by PerfAgent evaluate; import external results after tool execution"
            if engine.lower() != "k6"
            else "k6 execution skipped by user",
        }
        k6_summary = {"metrics": {}}
    else:
        execution_result = run_k6(script_path, summary_path, timeseries_path, workspace.raw_dir / "execution.log")
        k6_summary = read_k6_summary(summary_path)
    state["execution_result"] = execution_result
    state["raw_k6_metrics"] = k6_summary
    write_json(summary_path, k6_summary)
    write_json(workspace.raw_dir / "execution_result.json", execution_result)

    aligned = align_k6_jsonl(timeseries_path, strategy) or fallback_aligned_timeseries(k6_summary)

    prometheus_query_templates = load_prometheus_query_config(prometheus_query_config_path)
    prometheus_metrics = collect_prometheus_metrics(
        prometheus_url,
        prometheus_service_label,
        query_templates=prometheus_query_templates,
    )
    dependency_metrics = collect_dependency_metrics(prometheus_url, prometheus_service_label, dependencies or [])
    state["raw_prometheus_metrics"] = prometheus_metrics
    write_json(workspace.raw_dir / "prometheus_metrics.json", prometheus_metrics)
    write_json(workspace.raw_dir / "dependency_metrics.json", dependency_metrics)

    profiling = collect_profiling_artifacts(profile_paths or [], workspace.raw_dir / "profiles")
    state["profiling_artifacts"] = profiling
    state["service_resources"] = service_resources or {}
    write_json(workspace.raw_dir / "profiling_artifacts.json", profiling)
    state["warnings"].extend(profiling.get("warnings", []))

    aligned = merge_prometheus_metrics(aligned, prometheus_metrics)
    aligned = merge_dependency_metrics(aligned, dependency_metrics)
    aligned_path = write_aligned_csv(workspace.processed_dir / "aligned_timeseries.csv", aligned)
    state["aligned_timeseries_path"] = str(aligned_path)

    features = extract_features(
        k6_summary,
        aligned,
        slo_p95_ms=slo_p95_ms,
        slo_error_rate_percent=slo_error_rate_percent,
    )
    dependency_analysis = analyze_dependencies(dependencies or [], aligned)
    features["dependency_findings"] = dependency_analysis["findings"]
    state["dependency_analysis"] = dependency_analysis
    write_json(workspace.processed_dir / "dependency_analysis.json", dependency_analysis)
    state["features"] = features
    state["release_decision"] = features["release_decision"]
    write_json(workspace.processed_dir / "features.json", features)

    bottleneck = classify_bottleneck(features)
    state["bottleneck_analysis"] = bottleneck
    write_json(workspace.processed_dir / "bottleneck_analysis.json", bottleneck)

    reports = render_reports(
        output_dir=output_dir,
        service_name=service_name,
        runtime=runtime,
        target_url=target_url,
        strategy=strategy,
        contract_analysis=contract,
        features=features,
        bottleneck_analysis=bottleneck,
        profiling_artifacts=profiling,
        service_resources=service_resources or {},
        dependency_analysis=dependency_analysis,
        aligned_timeseries=aligned,
    )
    state["report_md_path"] = str(reports["report_md_path"])
    state["report_html_path"] = str(reports["report_html_path"])
    workspace.write_state(state)
    return state


def generate_only(*, service_name: str, openapi_path: Path, target_url: str, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    contract = parse_openapi(openapi_path, service_name)
    strategy = default_strategy("1m", 500, 1)
    test_data = generate_test_data(contract)
    write_json(output_dir / "contract_analysis.json", contract)
    write_json(output_dir / "test_data.json", test_data)
    write_yaml(output_dir / "test_strategy.yaml", strategy)
    script_path = generate_k6_script(contract, test_data, strategy, target_url, output_dir / "perf_test.js")
    locust_path = generate_locustfile(contract, test_data, target_url, output_dir / "locustfile.py")
    jmeter_path = generate_jmeter_plan(contract, test_data, strategy, target_url, output_dir / "jmeter_test_plan.jmx")
    grpc_path = generate_grpc_load_test(
        service_name=service_name,
        target=target_url.replace("http://", "").replace("https://", ""),
        proto_path="./protos/service.proto",
        output_path=output_dir / "grpc_load.py",
    )
    websocket_path = generate_websocket_load_test(
        service_name=service_name,
        target_url=target_url.replace("http://", "ws://").replace("https://", "wss://"),
        output_path=output_dir / "websocket_load.py",
    )
    return {
        "contract_analysis": output_dir / "contract_analysis.json",
        "test_data": output_dir / "test_data.json",
        "k6_script": script_path,
        "locustfile": locust_path,
        "jmeter_plan": jmeter_path,
        "grpc_load": grpc_path,
        "websocket_load": websocket_path,
    }


def import_external_results(
    *,
    run_dir: Path,
    tool: str,
    result_path: Path,
    service_name: str,
    runtime: str,
    target_url: str,
    slo_p95_ms: int,
    slo_error_rate_percent: float,
    service_resources: dict[str, Any] | None = None,
    dependency_analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw_summary, aligned = load_external_results(tool, result_path)
    workspace = Workspace(run_dir)
    workspace.create()
    write_json(workspace.raw_dir / f"{tool.lower()}_summary.json", raw_summary)
    aligned_path = write_aligned_csv(workspace.processed_dir / "aligned_timeseries.csv", aligned)
    features = extract_features(
        raw_summary,
        aligned,
        slo_p95_ms=slo_p95_ms,
        slo_error_rate_percent=slo_error_rate_percent,
    )
    features["source_tool"] = tool.lower()
    write_json(workspace.processed_dir / "features.json", features)
    bottleneck = classify_bottleneck(features)
    write_json(workspace.processed_dir / "bottleneck_analysis.json", bottleneck)
    contract = _read_json_or_empty(workspace.processed_dir / "contract_analysis.json")
    strategy = _read_json_or_empty(workspace.processed_dir / "test_strategy.yaml")
    if not strategy:
        strategy = {"duration": "external", "stages": [], "phases": [{"name": "external", "duration": "external"}]}
    reports = render_reports(
        output_dir=run_dir,
        service_name=service_name,
        runtime=runtime,
        target_url=target_url,
        strategy=strategy,
        contract_analysis=contract,
        features=features,
        bottleneck_analysis=bottleneck,
        profiling_artifacts={},
        service_resources=service_resources or {},
        dependency_analysis=dependency_analysis or {"dependencies": [], "findings": []},
        aligned_timeseries=aligned,
    )
    return {
        "tool": tool.lower(),
        "features": features,
        "bottleneck_analysis": bottleneck,
        "aligned_timeseries_path": str(aligned_path),
        "report_html_path": str(reports["report_html_path"]),
    }


def _read_json_or_empty(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    if path.suffix in {".yaml", ".yml"}:
        import yaml

        return yaml.safe_load(path.read_text()) or {}
    return read_json(path)


def _metric_contract(state: EvaluationState, strategy: dict[str, Any]) -> dict[str, Any]:
    return {
        "service": state["service_name"],
        "runtime": state["runtime"],
        "slo": {
            "p95_latency_ms": state["slo_p95_ms"],
            "error_rate_percent": state["slo_error_rate_percent"],
        },
        "test_phases": {phase["name"]: phase["duration"] for phase in strategy.get("phases", [])},
        "required_timeseries": {
            "load": ["rps", "p95_latency_ms", "p99_latency_ms", "error_rate_percent", "virtual_users"],
            "service": ["request_rate", "service_p95_latency", "service_error_rate"],
            "infra": ["cpu_usage_percent", "memory_working_set_mb", "cpu_throttling_percent", "pod_restarts"],
        },
        "dependencies": [
            {
                "name": dependency.get("name"),
                "type": dependency.get("type"),
                "role": dependency.get("role", "downstream"),
                "criticality": dependency.get("criticality", "medium"),
                "metrics": list((dependency.get("metrics") or {}).keys()),
            }
            for dependency in state.get("dependencies", [])
        ],
        "derived_features": [
            "stable_rps",
            "peak_rps",
            "breaking_point_rps",
            "first_slo_breach",
            "max_p95_latency",
            "max_error_rate",
            "cpu_per_1000_rps",
            "memory_growth_rate",
            "bottleneck_classification",
        ],
    }
