from langgraph.graph import StateGraph, START, END

from src.incident.state import IncidentState
from src.incident.agents import emit


def _scribe(state: IncidentState) -> dict:
    inc = state["incident"]
    lines = [f"# Postmortem — {inc['title']}", "",
             f"- Severity: {inc['severity']}",
             f"- Affected: {', '.join(inc.get('affected_services', []))}",
             f"- Signal: {inc.get('signal', '')}", "", "## Timeline", ""]
    for e in state.get("timeline", []):
        lines.append(
            f"- `{e.get('ts','')}` **{e.get('actor','')}** "
            f"({e.get('phase','')}): {e.get('text','')}"
        )
    md = "\n".join(lines)
    update = emit("postmortem", "Scribe", "postmortem", "action", "Postmortem drafted from timeline.")
    update["findings"] = {"postmortem_md": md}
    return update


def _action_items(state: IncidentState) -> dict:
    items = [
        "Add/verify alerting threshold for the affected SLO.",
        "Review runbook accuracy against this incident.",
        "Confirm on-call coverage and escalation path.",
    ]
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
