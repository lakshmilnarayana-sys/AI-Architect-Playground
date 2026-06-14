from __future__ import annotations

from pathlib import Path

from perfagent.core.state import EvaluationState
from perfagent.generators.k6_generator import generate_k6_script


def generate_k6(state: EvaluationState) -> EvaluationState:
    script_path = Path(state["output_dir"]) / "generated" / "perf_test.js"
    state["generated_k6_script_path"] = str(
        generate_k6_script(
            state["contract_analysis"],
            state["test_data"],
            state["test_strategy"],
            state["target_url"],
            script_path,
        )
    )
    return state

