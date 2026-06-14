from __future__ import annotations

from pathlib import Path

from perfagent.collectors.prometheus_collector import collect_prometheus_metrics, load_prometheus_query_config
from perfagent.core.state import EvaluationState


def collect_timeseries(state: EvaluationState) -> EvaluationState:
    config_path = state.get("prometheus_query_config_path")
    state["raw_prometheus_metrics"] = collect_prometheus_metrics(
        state.get("prometheus_url"),
        state.get("prometheus_service_label"),
        query_templates=load_prometheus_query_config(Path(config_path)) if config_path else None,
    )
    return state
