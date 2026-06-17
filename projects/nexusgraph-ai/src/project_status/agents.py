from src.project_status.state import ProjectStatusState


def status_from_counts(open_blockers: int, high_risks: int) -> str:
    if open_blockers >= 2 or high_risks >= 2:
        return "Red"
    if open_blockers == 1 or high_risks == 1:
        return "Yellow"
    return "Green"


def collect_status(project_record: dict) -> ProjectStatusState:
    snapshots = sorted(project_record.get("snapshots", []), key=lambda item: item["week"])
    if not snapshots:
        raise ValueError(f"Project has no snapshots: {project_record['project']}")

    current = snapshots[-1]
    previous = snapshots[-2] if len(snapshots) > 1 else {}
    return {
        "project": project_record["project"],
        "owner": project_record.get("owner", ""),
        "current_week": project_record.get("current_week", current["week"]),
        "current_snapshot": current,
        "previous_snapshot": previous,
    }


def analyze_risks(state: ProjectStatusState) -> dict:
    current = state["current_snapshot"]
    blockers = sorted(current.get("blockers", []), key=lambda item: item["id"])
    risks = sorted(current.get("risks", []), key=lambda item: item["id"])
    open_blockers = [item for item in blockers if item.get("status") != "Closed"]
    high_risks = [item for item in risks if item.get("severity") == "High"]

    return {
        "risks": risks,
        "blockers": blockers,
        "overall_status": status_from_counts(len(open_blockers), len(high_risks)),
    }


def analyze_dependencies(state: ProjectStatusState) -> dict:
    current = state["current_snapshot"]
    dependencies = sorted(current.get("dependencies", []), key=lambda item: item["id"])
    return {"dependencies": dependencies}


def build_insights(state: ProjectStatusState) -> list[dict]:
    current = state["current_snapshot"]
    previous = state.get("previous_snapshot") or {}
    insights: list[dict] = []

    if previous:
        current_progress = int(current.get("progress_percent", 0))
        previous_progress = int(previous.get("progress_percent", 0))
        metrics = current.get("metrics", {})
        previous_metrics = previous.get("metrics", {})
        insights.append(
            {
                "week_over_week": {
                    "from_week": previous["week"],
                    "to_week": current["week"],
                    "progress_delta": current_progress - previous_progress,
                    "completed_ticket_delta": int(metrics.get("completed_tickets", 0))
                    - int(previous_metrics.get("completed_tickets", 0)),
                    "merged_pr_delta": int(metrics.get("merged_prs", 0))
                    - int(previous_metrics.get("merged_prs", 0)),
                    "health_change": f"{previous.get('health', 'Unknown')} -> {current.get('health', 'Unknown')}",
                }
            }
        )

    at_risk_milestones = [
        item
        for item in current.get("milestones", [])
        if item.get("status") in {"At Risk", "Blocked"}
    ]
    if at_risk_milestones:
        insights.append(
            {
                "milestone_attention": [
                    f"{item['name']} is {item['status']}" for item in at_risk_milestones
                ]
            }
        )

    return insights


def render_executive_summary(state: ProjectStatusState) -> dict:
    current = state["current_snapshot"]
    risks = state.get("risks", [])
    blockers = state.get("blockers", [])
    dependencies = state.get("dependencies", [])
    summary = (
        f"{state['project']} is {state['overall_status']} for {state['current_week']}. "
        f"{current['summary']} "
        f"There are {len(blockers)} blocker(s), {len(risks)} tracked risk(s), "
        f"and {len(dependencies)} dependency item(s) requiring coordination."
    )

    next_actions = []
    next_actions.extend(f"Resolve blocker: {item['title']} ({item['owner']})." for item in blockers[:2])
    next_actions.extend(
        f"Mitigate risk: {item['title']} - {item['mitigation']}" for item in risks[:2]
    )
    next_actions.extend(
        f"Follow dependency: {item['name']} with {item['owner']}." for item in dependencies[:2]
    )

    return {
        "executive_summary": summary,
        "next_actions": next_actions[:5],
    }
