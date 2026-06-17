from langgraph.graph import StateGraph, START, END

from src.incident.state import IncidentState
from src.incident.agents import emit


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
    update = emit("postmortem", "Scribe", "postmortem", "action", "Postmortem drafted from timeline.")
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


def build_postmortem_subgraph(llm=None):
    g = StateGraph(IncidentState)
    g.add_node("scribe", _scribe)
    g.add_node("actions", _action_items)
    g.add_edge(START, "scribe")
    g.add_edge("scribe", "actions")
    g.add_edge("actions", END)
    return g.compile()
