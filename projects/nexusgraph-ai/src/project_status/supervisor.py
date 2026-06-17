from src.project_status.agents import (
    analyze_dependencies,
    analyze_risks,
    build_insights,
    collect_status,
    render_executive_summary,
)
from src.project_status.snapshots import get_project_snapshot


def run_project_status(project_name: str) -> dict:
    project_record = get_project_snapshot(project_name)
    state = collect_status(project_record)
    state.update(analyze_risks(state))
    state.update(analyze_dependencies(state))
    state["insights"] = build_insights(state)
    state.update(render_executive_summary(state))

    return {
        "project": state["project"],
        "owner": state["owner"],
        "week": state["current_week"],
        "overall_status": state["overall_status"],
        "risks": state["risks"],
        "blockers": state["blockers"],
        "dependencies": state["dependencies"],
        "insights": state["insights"],
        "executive_summary": state["executive_summary"],
        "next_actions": state["next_actions"],
    }
