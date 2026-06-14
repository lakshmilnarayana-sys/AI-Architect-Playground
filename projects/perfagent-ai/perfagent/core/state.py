from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Optional, TypedDict


class EvaluationState(TypedDict, total=False):
    run_id: str
    service_name: str
    openapi_path: str
    target_url: str
    runtime: str
    output_dir: str
    slo_p95_ms: int
    slo_error_rate_percent: float
    duration: str
    engine: str
    mode: str
    prometheus_url: Optional[str]
    prometheus_service_label: Optional[str]
    prometheus_query_config_path: Optional[str]
    contract_analysis: dict[str, Any]
    test_strategy: dict[str, Any]
    test_data: dict[str, Any]
    generated_k6_script_path: str
    execution_result: dict[str, Any]
    raw_k6_metrics: dict[str, Any]
    raw_prometheus_metrics: dict[str, Any]
    profiling_artifacts: dict[str, Any]
    service_resources: dict[str, Any]
    dependencies: list[dict[str, Any]]
    dependency_analysis: dict[str, Any]
    protocol_analysis: dict[str, Any]
    profile_phase_correlation: dict[str, Any]
    timeseries_analysis: dict[str, Any]
    react_reasoning: dict[str, Any]
    aligned_timeseries: list[dict[str, Any]]
    ai_analysis: dict[str, Any]
    aligned_timeseries_path: str
    features: dict[str, Any]
    bottleneck_analysis: dict[str, Any]
    report_md_path: str
    report_html_path: str
    release_decision: str
    errors: list[str]
    warnings: list[str]


def new_run_id(service_name: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    normalized = "".join(ch if ch.isalnum() else "-" for ch in service_name.lower()).strip("-")
    return f"perf-run-{stamp}-{normalized}"


def initial_state(
    *,
    service_name: str,
    openapi_path: str,
    target_url: str,
    runtime: str,
    output_dir: str,
    slo_p95_ms: int,
    slo_error_rate_percent: float,
    duration: str,
    engine: str = "k6",
    mode: str = "standard",
    prometheus_url: str | None = None,
    prometheus_service_label: str | None = None,
    prometheus_query_config_path: str | None = None,
    service_resources: dict[str, Any] | None = None,
    dependencies: list[dict[str, Any]] | None = None,
    llm: dict[str, Any] | None = None,
) -> EvaluationState:
    return {
        "run_id": new_run_id(service_name),
        "service_name": service_name,
        "openapi_path": openapi_path,
        "target_url": target_url,
        "runtime": runtime,
        "output_dir": output_dir,
        "slo_p95_ms": slo_p95_ms,
        "slo_error_rate_percent": slo_error_rate_percent,
        "duration": duration,
        "engine": engine,
        "mode": mode,
        "prometheus_url": prometheus_url,
        "prometheus_service_label": prometheus_service_label,
        "prometheus_query_config_path": prometheus_query_config_path,
        "contract_analysis": {},
        "test_strategy": {},
        "test_data": {},
        "generated_k6_script_path": "",
        "execution_result": {},
        "raw_k6_metrics": {},
        "raw_prometheus_metrics": {},
        "profiling_artifacts": {},
        "service_resources": service_resources or {},
        "dependencies": dependencies or [],
        "dependency_analysis": {},
        "protocol_analysis": {},
        "profile_phase_correlation": {},
        "timeseries_analysis": {},
        "react_reasoning": {},
        "aligned_timeseries": [],
        "ai_analysis": {},
        "llm": llm or {"enabled": False},
        "aligned_timeseries_path": "",
        "features": {},
        "bottleneck_analysis": {},
        "report_md_path": "",
        "report_html_path": "",
        "release_decision": "UNKNOWN",
        "errors": [],
        "warnings": [],
    }
