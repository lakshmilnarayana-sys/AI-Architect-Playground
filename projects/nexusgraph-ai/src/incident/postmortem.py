from langgraph.graph import StateGraph, START, END

from src.incident.state import IncidentState
from src.incident.agents import emit


def _live_summary(state: IncidentState) -> dict:
    timeline = [
        {
            "ts": event.get("ts", ""),
            "actor": event.get("actor", ""),
            "phase": event.get("phase", ""),
            "text": event.get("text", ""),
        }
        for event in state.get("timeline", [])
    ]
    summary = {
        "channel": ((state.get("findings") or {}).get("slack_channel") or {}).get("channel"),
        "message_count": len(state.get("slack_messages") or []),
        "timeline": timeline,
        "latest_summary": "Incident mitigated; collecting final timeline, actions, and customer update approval.",
    }
    update = emit(
        "postmortem",
        "Scribe Agent",
        "postmortem",
        "action",
        "Summarized Slack channel contributions and captured the incident timeline.",
    )
    update["findings"] = {"scribe_summary": summary}
    return update


def _status_update(state: IncidentState) -> dict:
    incident = state["incident"]
    findings = state.get("findings") or {}
    recovered = bool(findings.get("slo_recovered"))
    text = (
        f"{incident['title']} has been mitigated and service health is recovering. "
        "Teams continue to monitor for recurrence."
        if recovered
        else f"{incident['title']} remains under investigation. Mitigation is in progress."
    )
    status_update = {
        "text": text,
        "targets": ["slack", "status_page"],
        "requires_human_approval": True,
        "approved": False,
    }
    update = emit(
        "postmortem",
        "Scribe Agent",
        "postmortem",
        "gate",
        "Human approval required before publishing status update to Slack and status page.",
    )
    update["findings"] = {"status_update": status_update}
    update["approvals"] = {
        "status_update": {
            "required": True,
            "approved": False,
            "reason": "Publish to Slack and status page requires human-in-the-loop review.",
        }
    }
    update["status_page"] = {"pending_update": status_update}
    return update


def _scribe(state: IncidentState) -> dict:
    inc = state["incident"]
    findings = state.get("findings") or {}
    runtime = findings.get("kubernetes_runtime") or state.get("runtime") or {}
    automation = findings.get("automation") or {}
    lines = [f"# Postmortem — {inc['title']}", "",
             f"- Severity: {inc['severity']}",
             f"- Affected: {', '.join(inc.get('affected_services', []))}",
             f"- Signal: {inc.get('signal', '')}",
             f"- Failure mode: {inc.get('failure_mode', 'not modeled')}",
             f"- Kubernetes status: {runtime.get('pod_status', 'not captured')}",
             "", "## Timeline", ""]
    for e in state.get("timeline", []):
        lines.append(
            f"- `{e.get('ts','')}` **{e.get('actor','')}** "
            f"({e.get('phase','')}): {e.get('text','')}"
        )
    if state.get("logs"):
        lines.extend(["", "## Static production logs", ""])
        for log in state["logs"][:5]:
            lines.append(f"- `{log.get('timestamp') or log.get('ts','')}` {log.get('message','')}")
    if state.get("observability"):
        lines.extend(["", "## Observability evidence", ""])
        for item in state["observability"][:5]:
            lines.append(f"- {item.get('kind', 'evidence')}: {item.get('name', '')}")
    if automation:
        lines.extend(["", "## Runbook automation", ""])
        lines.append(f"- Incident channel: {automation.get('channel', 'not created')}")
        lines.append(f"- Tracking ticket: {automation.get('ticket', 'not created')}")
        lines.append(f"- Status update draft: {automation.get('status_update', '')}")
    md = "\n".join(lines)
    update = emit("postmortem", "Scribe Agent", "postmortem", "action", "Postmortem drafted from timeline.")
    update["findings"] = {"postmortem_md": md}
    return update


def _action_items(state: IncidentState) -> dict:
    failure_mode = state["incident"].get("failure_mode")
    items = [
        "Add/verify alerting threshold for the affected SLO.",
        "Review runbook accuracy against this incident.",
        "Confirm on-call coverage and escalation path.",
    ]
    if failure_mode:
        items.append(f"Create prevention work item for recurring {failure_mode} incidents.")
    if state.get("observability"):
        items.append("Attach dashboard, alert, and trace links to the incident review.")
    update = emit("postmortem", "ActionItemAgent", "postmortem", "finding",
                  f"{len(items)} follow-up action item(s) created.")
    update["findings"] = {"action_items": items}
    return update


def _save_jira(state: IncidentState) -> dict:
    from src.incident.jira import save_incident

    issue = save_incident(state)
    update = emit(
        "postmortem",
        "Jira Agent",
        "postmortem",
        "action",
        f"Saved simulated incident to Jira as {issue['key']}.",
    )
    update["findings"] = {"jira_issue": issue}
    return update


def build_postmortem_subgraph(llm=None):
    g = StateGraph(IncidentState)
    g.add_node("live_summary", _live_summary)
    g.add_node("status_update", _status_update)
    g.add_node("scribe", _scribe)
    g.add_node("actions", _action_items)
    g.add_node("save_jira", _save_jira)
    g.add_edge(START, "live_summary")
    g.add_edge("live_summary", "status_update")
    g.add_edge("status_update", "scribe")
    g.add_edge("scribe", "actions")
    g.add_edge("actions", "save_jira")
    g.add_edge("save_jira", END)
    return g.compile()
