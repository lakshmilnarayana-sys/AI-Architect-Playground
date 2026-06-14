from __future__ import annotations

from pathlib import Path

from perfagent.collectors.k6_collector import read_k6_summary, run_k6
from perfagent.core.state import EvaluationState


def execute_k6(state: EvaluationState) -> EvaluationState:
    output_dir = Path(state["output_dir"])
    summary_path = output_dir / "raw" / "k6_summary.json"
    timeseries_path = output_dir / "raw" / "k6_timeseries.jsonl"
    state["execution_result"] = run_k6(
        Path(state["generated_k6_script_path"]),
        summary_path,
        timeseries_path,
        output_dir / "raw" / "execution.log",
    )
    state["raw_k6_metrics"] = read_k6_summary(summary_path)
    return state
