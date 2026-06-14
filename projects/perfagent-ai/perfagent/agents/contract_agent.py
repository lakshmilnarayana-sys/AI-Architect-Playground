from __future__ import annotations

from pathlib import Path

from perfagent.core.state import EvaluationState
from perfagent.parsers.openapi_parser import parse_openapi


def analyze_contract(state: EvaluationState) -> EvaluationState:
    state["contract_analysis"] = parse_openapi(Path(state["openapi_path"]), state["service_name"])
    return state

