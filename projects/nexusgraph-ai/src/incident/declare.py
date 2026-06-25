from functools import partial

from langgraph.graph import StateGraph, START, END

from src.incident.state import IncidentState
from src.incident.agents import emit, phrase
from src.incident.alerting import evaluate_alert


def _alert(state: IncidentState) -> dict:
    alert = evaluate_alert(state["incident"])
    text = (
        f"Observability alert triggered by {alert['source']}: "
        f"{alert['metric']} crossed threshold {alert['threshold']}."
        if alert["triggered"]
        else "Observability Agent did not find a threshold breach."
    )
    update = emit("declare", "Observability Agent", "bot", "finding", text)
    update["findings"] = {"alert": alert}
    return update


def _intake(state: IncidentState, llm=None) -> dict:
    inc = state["incident"]
    text = phrase(
        llm,
        f"Announce incident declaration for {inc['title']} given signal: {inc['signal']}",
        fallback=(
            f"Incident Commander Agent declares {inc['severity']} · "
            f"{inc['title']} — {inc['signal']}"
        ),
    )
    from src.incident.slack import post_to_slack, channel_name
    post_to_slack(channel_name(state["incident"]), text, username="incident-commander")

    update = {"phase": "declare", **emit("declare", "Incident Commander Agent", "commander", "message", text)}
    update["findings"] = {
        "incident_commander": {
            "name": "Incident Commander Agent",
            "role": "primary_orchestrator",
            "responsibility": "Direct agents, approve transitions, verify mitigation, and close the incident loop.",
        }
    }
    return update


def _severity(state: IncidentState, llm=None) -> dict:
    sev = state["incident"]["severity"]
    update = emit("declare", "Severity Classifier", "commander", "finding",
                  f"Severity confirmed: {sev}")
    update["findings"] = {"severity": sev}
    return update


def build_declare_subgraph(llm=None):
    g = StateGraph(IncidentState)
    g.add_node("alert", _alert)
    g.add_node("intake", partial(_intake, llm=llm))
    g.add_node("severity", partial(_severity, llm=llm))
    g.add_edge(START, "alert")
    g.add_edge("alert", "intake")
    g.add_edge("intake", "severity")
    g.add_edge("severity", END)
    return g.compile()
