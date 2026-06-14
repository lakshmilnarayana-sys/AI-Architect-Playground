from __future__ import annotations

from pathlib import Path

from perfagent.analyzers.alignment import fallback_aligned_timeseries, write_aligned_csv
from perfagent.core.state import EvaluationState


def align_timeseries(state: EvaluationState) -> EvaluationState:
    rows = fallback_aligned_timeseries(state.get("raw_k6_metrics", {}))
    state["aligned_timeseries_path"] = str(
        write_aligned_csv(Path(state["output_dir"]) / "processed" / "aligned_timeseries.csv", rows)
    )
    return state

