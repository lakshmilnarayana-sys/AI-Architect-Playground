from __future__ import annotations

from perfagent.analyzers.bottlenecks import classify_bottleneck
from perfagent.core.state import EvaluationState


def analyze_bottleneck(state: EvaluationState) -> EvaluationState:
    state["bottleneck_analysis"] = classify_bottleneck(state["features"])
    return state

