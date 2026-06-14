from __future__ import annotations

from perfagent.config import default_strategy
from perfagent.core.state import EvaluationState


def create_strategy(state: EvaluationState) -> EvaluationState:
    state["test_strategy"] = default_strategy(
        state.get("duration", "10m"),
        state["slo_p95_ms"],
        state["slo_error_rate_percent"],
    )
    return state

