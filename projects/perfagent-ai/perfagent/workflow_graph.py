from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict

from perfagent.core.state import EvaluationState
from perfagent.workflow import evaluate_service


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
    service_resources: dict[str, Any] | None
    dependencies: list[dict[str, Any]] | None
    llm: dict[str, Any] | None
    traffic_profile_config: dict[str, Any] | None
    observability_config: dict[str, Any] | None
    protocol_config: dict[str, Any] | None
    storage: dict[str, Any] | None
    prometheus_url: str | None
    prometheus_service_label: str | None
    prometheus_query_config_path: Path | None
    profile_paths: list[Path] | None
    skip_run: bool
    result: EvaluationState


def run_langgraph_evaluation(**kwargs: Any) -> EvaluationState:
    """Run PerfAgent through a LangGraph wrapper when langgraph is installed."""
    try:
        from langgraph.graph import END, StateGraph
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("LangGraph workflow requires perfagent-ai[graph] or langgraph installed.") from exc

    def evaluate_node(state: GraphInput) -> GraphInput:
        state["result"] = evaluate_service(**{key: value for key, value in state.items() if key != "result"})
        return state

    graph = StateGraph(GraphInput)
    graph.add_node("evaluate_service", evaluate_node)
    graph.set_entry_point("evaluate_service")
    graph.add_edge("evaluate_service", END)
    compiled = graph.compile()
    result = compiled.invoke(kwargs)
    return result["result"]
