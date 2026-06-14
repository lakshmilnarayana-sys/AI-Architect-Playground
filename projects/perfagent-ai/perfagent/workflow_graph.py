from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, TypedDict

from perfagent.analyzers.alignment import align_k6_jsonl, fallback_aligned_timeseries, write_aligned_csv
from perfagent.analyzers.bottlenecks import classify_bottleneck
from perfagent.analyzers.dependencies import analyze_dependencies
from perfagent.analyzers.features import extract_features
from perfagent.analyzers.protocols import analyze_protocol_metrics
from perfagent.analyzers.timeseries_reasoning import analyze_timeseries, reason_over_timeseries
from perfagent.collectors.k6_collector import read_k6_summary, run_k6
from perfagent.collectors.observability_adapters import collect_observability_traffic_profile
from perfagent.collectors.profiling_collector import (
    build_profile_capture_plan,
    collect_profiling_artifacts,
    finish_profile_capture_plan,
    start_profile_capture_plan,
)
from perfagent.collectors.protocol_collectors import duration_to_seconds, run_protocol_script
from perfagent.collectors.prometheus_collector import (
    collect_dependency_metrics,
    collect_prometheus_metrics,
    load_prometheus_query_config,
    merge_dependency_metrics,
    merge_prometheus_metrics,
)
from perfagent.collectors.traffic_profile import collect_prometheus_traffic_profile
from perfagent.collectors.traffic_replay import apply_replay_plan_to_strategy, build_traffic_replay_plan
from perfagent.config import default_strategy, derive_strategy_from_traffic_profile
from perfagent.core.artifacts import write_json, write_yaml
from perfagent.core.state import EvaluationState, initial_state
from perfagent.core.workspace import Workspace
from perfagent.generators.grpc_generator import generate_grpc_load_test
from perfagent.generators.jmeter_generator import generate_jmeter_plan
from perfagent.generators.k6_generator import generate_k6_script
from perfagent.generators.locust_generator import generate_locustfile
from perfagent.generators.report_renderer import render_reports
from perfagent.generators.synthetic_data import generate_test_data
from perfagent.generators.ui_generator import generate_ui_journey_test
from perfagent.generators.websocket_generator import generate_websocket_load_test
from perfagent.parsers.openapi_parser import parse_openapi
from perfagent.workflow import _index_run_vectors, _metric_contract, _persist_run, _run_ai_analysis


class GraphInput(TypedDict, total=False):
    service_name: str
    openapi_path: Path
    target_url: str
    runtime: str
    slo_p95_ms: int
    slo_error_rate_percent: float
    duration: str
    output_dir: Path
    engine: str
    mode: str
    capacity_probe_rps: int | None
    service_resources: dict[str, Any] | None
    dependencies: list[dict[str, Any]] | None
    llm: dict[str, Any] | None
    traffic_profile_config: dict[str, Any] | None
    observability_config: dict[str, Any] | None
    protocol_config: dict[str, Any] | None
    profiling_config: dict[str, Any] | None
    storage: dict[str, Any] | None
    prometheus_url: str | None
    prometheus_service_label: str | None
    prometheus_query_config_path: Path | None
    profile_paths: list[Path] | None
    skip_run: bool
    evaluation_state: EvaluationState
    workspace: Workspace
    contract: dict[str, Any]
    traffic_profile: dict[str, Any]
    replay_plan: dict[str, Any]
    strategy: dict[str, Any]
    test_data: dict[str, Any]
    grpc_script_path: Path
    websocket_script_path: Path
    ui_script_path: Path
    k6_summary: dict[str, Any]
    aligned_timeseries: list[dict[str, Any]]
    dependency_metrics: dict[str, Any]
    profiling_artifacts: dict[str, Any]
    profile_capture_plan: dict[str, Any]
    profile_capture_context: dict[str, Any]
    profile_capture_result: dict[str, Any]
    features: dict[str, Any]
    dependency_analysis: dict[str, Any]
    timeseries_analysis: dict[str, Any]
    react_reasoning: dict[str, Any]
    bottleneck_analysis: dict[str, Any]
    ai_analysis: dict[str, Any]
    result: EvaluationState


StageFunction = Callable[[GraphInput], GraphInput]


def run_langgraph_evaluation(**kwargs: Any) -> EvaluationState:
    """Run PerfAgent through a multi-node LangGraph workflow when installed."""
    try:
        from langgraph.graph import END, StateGraph
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("LangGraph workflow requires perfagent-ai[graph] or langgraph installed.") from exc

    stages = _stage_nodes()
    graph = StateGraph(GraphInput)
    for node_name, stage_func in stages:
        graph.add_node(node_name, stage_func)
    graph.set_entry_point(stages[0][0])
    for (node_name, _), (next_node_name, _) in zip(stages, stages[1:]):
        graph.add_edge(node_name, next_node_name)
    graph.add_edge(stages[-1][0], END)

    compiled = graph.compile()
    result = compiled.invoke(kwargs)
    return result["result"]


def _stage_nodes() -> list[tuple[str, StageFunction]]:
    return [
        ("initialize_workspace", _stage_initialize_workspace),
        ("analyze_contract", _stage_analyze_contract),
        ("plan_strategy", _stage_plan_strategy),
        ("generate_tests", _stage_generate_tests),
        ("execute_load", _stage_execute_load),
        ("collect_signals", _stage_collect_signals),
        ("analyze_results", _stage_analyze_results),
        ("render_report", _stage_render_report),
    ]


def _stage_initialize_workspace(state: GraphInput) -> GraphInput:
    output_dir = Path(state["output_dir"])
    evaluation_state = initial_state(
        service_name=state["service_name"],
        openapi_path=str(state["openapi_path"]),
        target_url=state["target_url"],
        runtime=state["runtime"],
        output_dir=str(output_dir),
        slo_p95_ms=state["slo_p95_ms"],
        slo_error_rate_percent=state["slo_error_rate_percent"],
        duration=state["duration"],
        engine=state.get("engine", "k6"),
        mode=state.get("mode", "standard"),
        prometheus_url=state.get("prometheus_url"),
        prometheus_service_label=state.get("prometheus_service_label"),
        prometheus_query_config_path=str(state["prometheus_query_config_path"])
        if state.get("prometheus_query_config_path")
        else None,
        service_resources=state.get("service_resources"),
        dependencies=state.get("dependencies"),
        llm=state.get("llm"),
    )
    workspace = Workspace(output_dir)
    workspace.create()
    copied_openapi = workspace.copy_openapi(Path(state["openapi_path"]))
    evaluation_state["openapi_path"] = str(copied_openapi)
    state["output_dir"] = output_dir
    state["evaluation_state"] = evaluation_state
    state["workspace"] = workspace
    return state


def _stage_analyze_contract(state: GraphInput) -> GraphInput:
    evaluation_state = state["evaluation_state"]
    workspace = state["workspace"]
    contract = parse_openapi(Path(evaluation_state["openapi_path"]), state["service_name"])
    evaluation_state["contract_analysis"] = contract
    state["contract"] = contract
    write_json(workspace.processed_dir / "contract_analysis.json", contract)
    return state


def _stage_plan_strategy(state: GraphInput) -> GraphInput:
    evaluation_state = state["evaluation_state"]
    workspace = state["workspace"]
    traffic_profile_settings = state.get("traffic_profile_config") or {"enabled": False}
    if traffic_profile_settings.get("enabled") and traffic_profile_settings.get("source") not in {None, "prometheus"}:
        traffic_profile = collect_observability_traffic_profile(
            state.get("observability_config") or traffic_profile_settings,
            state["service_name"],
        )
    else:
        traffic_profile = collect_prometheus_traffic_profile(
            state.get("prometheus_url"),
            state.get("prometheus_service_label"),
            traffic_profile_settings,
        )
    write_json(workspace.processed_dir / "traffic_profile.json", traffic_profile)

    replay_plan = build_traffic_replay_plan(state["contract"], traffic_profile)
    write_json(workspace.processed_dir / "traffic_replay_plan.json", replay_plan)

    if traffic_profile.get("enabled") and traffic_profile.get("endpoint_mix"):
        strategy = derive_strategy_from_traffic_profile(
            traffic_profile,
            duration=state["duration"],
            slo_p95_ms=state["slo_p95_ms"],
            slo_error_rate_percent=state["slo_error_rate_percent"],
        )
        strategy = apply_replay_plan_to_strategy(strategy, replay_plan)
    else:
        strategy = default_strategy(
            state["duration"],
            state["slo_p95_ms"],
            state["slo_error_rate_percent"],
            mode=state.get("mode", "standard"),
            capacity_probe_rps=state.get("capacity_probe_rps"),
        )

    evaluation_state["test_strategy"] = strategy
    state["traffic_profile"] = traffic_profile
    state["replay_plan"] = replay_plan
    state["strategy"] = strategy
    write_yaml(workspace.processed_dir / "test_strategy.yaml", strategy)
    write_yaml(workspace.processed_dir / "metric_contract.yaml", _metric_contract(evaluation_state, strategy))
    return state


def _stage_generate_tests(state: GraphInput) -> GraphInput:
    evaluation_state = state["evaluation_state"]
    workspace = state["workspace"]
    protocol_config = state.get("protocol_config") or {}
    contract = state["contract"]
    strategy = state["strategy"]

    test_data = generate_test_data(contract)
    evaluation_state["test_data"] = test_data
    state["test_data"] = test_data
    write_json(workspace.generated_dir / "test_data.json", test_data)

    script_path = generate_k6_script(
        contract,
        test_data,
        strategy,
        state["target_url"],
        workspace.generated_dir / "perf_test.js",
    )
    evaluation_state["generated_k6_script_path"] = str(script_path)
    generate_locustfile(contract, test_data, state["target_url"], workspace.generated_dir / "locustfile.py")
    generate_jmeter_plan(
        contract,
        test_data,
        strategy,
        state["target_url"],
        workspace.generated_dir / "jmeter_test_plan.jmx",
    )
    state["grpc_script_path"] = generate_grpc_load_test(
        service_name=state["service_name"],
        target=state["target_url"].replace("http://", "").replace("https://", ""),
        proto_path=protocol_config.get("grpc", {}).get("proto_path", "./protos/service.proto"),
        output_path=workspace.generated_dir / "grpc_load.py",
        config=protocol_config.get("grpc", {}),
    )
    state["websocket_script_path"] = generate_websocket_load_test(
        service_name=state["service_name"],
        target_url=state["target_url"].replace("http://", "ws://").replace("https://", "wss://"),
        output_path=workspace.generated_dir / "websocket_load.py",
        config=protocol_config.get("websocket", {}),
    )
    state["ui_script_path"] = generate_ui_journey_test(
        service_name=state["service_name"],
        target_url=state["target_url"],
        output_path=workspace.generated_dir / "ui_journey.py",
        config=protocol_config.get("ui", {}),
    )
    return state


def _stage_execute_load(state: GraphInput) -> GraphInput:
    evaluation_state = state["evaluation_state"]
    workspace = state["workspace"]
    protocol_config = state.get("protocol_config") or {}
    summary_path = workspace.raw_dir / "k6_summary.json"
    timeseries_path = workspace.raw_dir / "k6_timeseries.jsonl"
    engine_name = state.get("engine", "k6").lower()

    protocol_aligned: list[dict[str, Any]] | None = None
    profiling_settings = state.get("profiling_config") or {}
    if profiling_settings.get("auto_capture"):
        profile_capture_plan = build_profile_capture_plan(
            runtime=state["runtime"],
            output_dir=workspace.raw_dir / "profiles" / "captured",
            duration_seconds=int(profiling_settings.get("duration_seconds", 60)),
            pid=profiling_settings.get("pid"),
            profile_endpoint=profiling_settings.get("profile_endpoint"),
            container=profiling_settings.get("container"),
            mode=str(profiling_settings.get("mode", "ebpf")),
        )
        write_json(workspace.raw_dir / "profile_capture_plan.json", profile_capture_plan)
        state["profile_capture_plan"] = profile_capture_plan
        state["profile_capture_context"] = start_profile_capture_plan(
            profile_capture_plan,
            log_dir=workspace.raw_dir / "profiles" / "logs",
        )
    if state.get("skip_run", False) or engine_name not in {"k6", "grpc", "websocket", "ui", "browser"}:
        execution_result: dict[str, Any] = {
            "exit_code": 0,
            "skipped": True,
            "summary_path": str(summary_path),
            "timeseries_path": str(timeseries_path),
            "stdout": "",
            "stderr": f"{state.get('engine', 'k6')} execution skipped by PerfAgent evaluate; "
            "import external results after tool execution"
            if engine_name != "k6"
            else "k6 execution skipped by user",
        }
        k6_summary = {"metrics": {}}
    elif engine_name in {"grpc", "websocket", "ui", "browser"}:
        script_path = _protocol_script_path(state, engine_name)
        ui_config = protocol_config.get("ui", {})
        execution_result, k6_summary, protocol_aligned = run_protocol_script(
            tool="ui" if engine_name == "browser" else engine_name,
            script_path=script_path,
            summary_path=summary_path,
            execution_log_path=workspace.raw_dir / "execution.log",
            duration_seconds=duration_to_seconds(state["duration"]),
            concurrency=max(
                1,
                int(ui_config.get("concurrency", state["strategy"].get("stages", [{}])[0].get("target", 10)) or 10),
            ),
        )
    else:
        execution_result = run_k6(
            Path(evaluation_state["generated_k6_script_path"]),
            summary_path,
            timeseries_path,
            workspace.raw_dir / "execution.log",
        )
        k6_summary = read_k6_summary(summary_path)

    evaluation_state["execution_result"] = execution_result
    evaluation_state["raw_k6_metrics"] = k6_summary
    if state.get("profile_capture_plan") and state.get("profile_capture_context"):
        profile_capture_result = finish_profile_capture_plan(
            state["profile_capture_plan"],
            state["profile_capture_context"],
            log_dir=workspace.raw_dir / "profiles" / "logs",
            timeout_seconds=max(15, int(profiling_settings.get("duration_seconds", 60)) + 30),
        )
        write_json(workspace.raw_dir / "profile_capture_result.json", profile_capture_result)
        state["profile_capture_result"] = profile_capture_result
    state["k6_summary"] = k6_summary
    if protocol_aligned is not None:
        state["aligned_timeseries"] = protocol_aligned
    write_json(summary_path, k6_summary)
    write_json(workspace.raw_dir / "execution_result.json", execution_result)
    return state


def _stage_collect_signals(state: GraphInput) -> GraphInput:
    evaluation_state = state["evaluation_state"]
    workspace = state["workspace"]
    timeseries_path = workspace.raw_dir / "k6_timeseries.jsonl"
    aligned = state.get("aligned_timeseries") or align_k6_jsonl(timeseries_path, state["strategy"])
    aligned = aligned or fallback_aligned_timeseries(state["k6_summary"])

    query_templates = load_prometheus_query_config(state.get("prometheus_query_config_path"))
    prometheus_metrics = collect_prometheus_metrics(
        state.get("prometheus_url"),
        state.get("prometheus_service_label"),
        query_templates=query_templates,
    )
    dependency_metrics = collect_dependency_metrics(
        state.get("prometheus_url"),
        state.get("prometheus_service_label"),
        state.get("dependencies") or [],
    )
    evaluation_state["raw_prometheus_metrics"] = prometheus_metrics
    write_json(workspace.raw_dir / "prometheus_metrics.json", prometheus_metrics)
    write_json(workspace.raw_dir / "dependency_metrics.json", dependency_metrics)

    profiling = collect_profiling_artifacts(state.get("profile_paths") or [], workspace.raw_dir / "profiles")
    if state.get("profile_capture_result"):
        profiling["auto_capture"] = state["profile_capture_result"]
        profiling["enabled"] = True
        profiling["warnings"].extend(state["profile_capture_result"].get("warnings", []))
    evaluation_state["profiling_artifacts"] = profiling
    evaluation_state["service_resources"] = state.get("service_resources") or {}
    evaluation_state["warnings"].extend(profiling.get("warnings", []))
    write_json(workspace.raw_dir / "profiling_artifacts.json", profiling)
    write_json(workspace.processed_dir / "profiling_summary.json", profiling)

    aligned = merge_prometheus_metrics(aligned, prometheus_metrics)
    aligned = merge_dependency_metrics(aligned, dependency_metrics)
    aligned_path = write_aligned_csv(workspace.processed_dir / "aligned_timeseries.csv", aligned)
    evaluation_state["aligned_timeseries_path"] = str(aligned_path)
    evaluation_state["aligned_timeseries"] = aligned
    state["aligned_timeseries"] = aligned
    state["dependency_metrics"] = dependency_metrics
    state["profiling_artifacts"] = profiling
    return state


def _stage_analyze_results(state: GraphInput) -> GraphInput:
    evaluation_state = state["evaluation_state"]
    workspace = state["workspace"]
    aligned = state["aligned_timeseries"]
    features = extract_features(
        state["k6_summary"],
        aligned,
        slo_p95_ms=state["slo_p95_ms"],
        slo_error_rate_percent=state["slo_error_rate_percent"],
    )
    dependency_analysis = analyze_dependencies(state.get("dependencies") or [], aligned)
    protocol_analysis = analyze_protocol_metrics(state["k6_summary"], aligned)
    features["dependency_findings"] = dependency_analysis["findings"]
    features["protocol_findings"] = protocol_analysis["findings"]
    evaluation_state["dependency_analysis"] = dependency_analysis
    evaluation_state["protocol_analysis"] = protocol_analysis
    write_json(workspace.processed_dir / "dependency_analysis.json", dependency_analysis)
    write_json(workspace.processed_dir / "protocol_analysis.json", protocol_analysis)

    timeseries_analysis = analyze_timeseries(
        aligned,
        slo_p95_ms=state["slo_p95_ms"],
        slo_error_rate_percent=state["slo_error_rate_percent"],
    )
    react_reasoning = reason_over_timeseries(
        timeseries_analysis=timeseries_analysis,
        features=features,
        dependency_analysis=dependency_analysis,
    )
    features["timeseries_reasoning_classification"] = react_reasoning["conclusion"]["classification"]
    features["timeseries_reasoning_confidence"] = react_reasoning["conclusion"]["confidence"]
    evaluation_state["timeseries_analysis"] = timeseries_analysis
    evaluation_state["react_reasoning"] = react_reasoning
    write_json(workspace.processed_dir / "timeseries_analysis.json", timeseries_analysis)
    write_json(workspace.processed_dir / "react_reasoning.json", react_reasoning)
    evaluation_state["features"] = features
    evaluation_state["release_decision"] = features["release_decision"]
    write_json(workspace.processed_dir / "features.json", features)

    bottleneck = classify_bottleneck(features)
    evaluation_state["bottleneck_analysis"] = bottleneck
    write_json(workspace.processed_dir / "bottleneck_analysis.json", bottleneck)

    ai_analysis = _run_ai_analysis(
        state.get("llm") or {"enabled": False},
        {
            "service": state["service_name"],
            "runtime": state["runtime"],
            "target_url": state["target_url"],
            "slo": {
                "p95_latency_ms": state["slo_p95_ms"],
                "error_rate_percent": state["slo_error_rate_percent"],
            },
            "features": features,
            "timeseries_analysis": timeseries_analysis,
            "react_reasoning": react_reasoning,
            "bottleneck_analysis": bottleneck,
            "dependency_analysis": dependency_analysis,
            "protocol_analysis": protocol_analysis,
            "metric_contract": _metric_contract(evaluation_state, state["strategy"]),
            "warnings": evaluation_state["warnings"],
        },
    )
    evaluation_state["ai_analysis"] = ai_analysis
    write_json(workspace.processed_dir / "ai_analysis.json", ai_analysis)
    state["features"] = features
    state["dependency_analysis"] = dependency_analysis
    state["protocol_analysis"] = protocol_analysis
    state["timeseries_analysis"] = timeseries_analysis
    state["react_reasoning"] = react_reasoning
    state["bottleneck_analysis"] = bottleneck
    state["ai_analysis"] = ai_analysis
    return state


def _stage_render_report(state: GraphInput) -> GraphInput:
    evaluation_state = state["evaluation_state"]
    workspace = state["workspace"]
    reports = render_reports(
        output_dir=Path(state["output_dir"]),
        service_name=state["service_name"],
        runtime=state["runtime"],
        target_url=state["target_url"],
        strategy=state["strategy"],
        contract_analysis=state["contract"],
        features=state["features"],
        bottleneck_analysis=state["bottleneck_analysis"],
        profiling_artifacts=state["profiling_artifacts"],
        service_resources=state.get("service_resources") or {},
        dependency_analysis=state["dependency_analysis"],
        protocol_analysis=state.get("protocol_analysis") or {"protocol_metrics": {}, "findings": [], "warnings": []},
        ai_analysis=state["ai_analysis"],
        traffic_profile=state["traffic_profile"],
        aligned_timeseries=state["aligned_timeseries"],
        timeseries_analysis=state["timeseries_analysis"],
        react_reasoning=state["react_reasoning"],
    )
    evaluation_state["report_md_path"] = str(reports["report_md_path"])
    evaluation_state["report_html_path"] = str(reports["report_html_path"])
    _persist_run(state.get("storage") or {}, evaluation_state, state["features"])
    _index_run_vectors(state.get("storage") or {}, evaluation_state)
    workspace.write_state(evaluation_state)
    state["result"] = evaluation_state
    return state


def _protocol_script_path(state: GraphInput, engine_name: str) -> Path:
    if engine_name == "grpc":
        return state["grpc_script_path"]
    if engine_name == "websocket":
        return state["websocket_script_path"]
    return state["ui_script_path"]
