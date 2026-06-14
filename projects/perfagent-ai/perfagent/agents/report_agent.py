from __future__ import annotations

from pathlib import Path

from perfagent.core.state import EvaluationState
from perfagent.generators.report_renderer import render_reports


def generate_report(state: EvaluationState) -> EvaluationState:
    reports = render_reports(
        output_dir=Path(state["output_dir"]),
        service_name=state["service_name"],
        runtime=state["runtime"],
        target_url=state["target_url"],
        strategy=state["test_strategy"],
        contract_analysis=state["contract_analysis"],
        features=state["features"],
        bottleneck_analysis=state["bottleneck_analysis"],
        profiling_artifacts=state.get("profiling_artifacts", {}),
        aligned_timeseries=[],
    )
    state["report_md_path"] = str(reports["report_md_path"])
    state["report_html_path"] = str(reports["report_html_path"])
    return state
