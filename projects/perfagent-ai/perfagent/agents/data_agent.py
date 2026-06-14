from __future__ import annotations

from perfagent.core.state import EvaluationState
from perfagent.generators.synthetic_data import generate_test_data


def generate_data(state: EvaluationState) -> EvaluationState:
    state["test_data"] = generate_test_data(state["contract_analysis"])
    return state

