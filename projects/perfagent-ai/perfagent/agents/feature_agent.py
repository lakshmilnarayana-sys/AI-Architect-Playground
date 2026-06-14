from __future__ import annotations

from perfagent.analyzers.alignment import fallback_aligned_timeseries
from perfagent.analyzers.features import extract_features
from perfagent.core.state import EvaluationState


def extract_performance_features(state: EvaluationState) -> EvaluationState:
    rows = fallback_aligned_timeseries(state.get("raw_k6_metrics", {}))
    state["features"] = extract_features(
        state.get("raw_k6_metrics", {}),
        rows,
        slo_p95_ms=state["slo_p95_ms"],
        slo_error_rate_percent=state["slo_error_rate_percent"],
    )
    state["release_decision"] = state["features"]["release_decision"]
    return state

