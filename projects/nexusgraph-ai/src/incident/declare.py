from functools import partial

from langgraph.graph import StateGraph, START, END

from src.incident.state import IncidentState
from src.incident.agents import emit, phrase


def _intake(state: IncidentState, llm=None) -> dict:
    inc = state["incident"]
    text = phrase(
        llm,
        f"Announce incident declaration for {inc['title']} given signal: {inc['signal']}",
        fallback=f"{inc['severity']} declared · {inc['title']} — {inc['signal']}",
    )
    return {"phase": "declare", **emit("declare", "Incident Bot", "bot", "message", text)}


def _severity(state: IncidentState, llm=None) -> dict:
    sev = state["incident"]["severity"]
    update = emit("declare", "Severity Classifier", "commander", "finding",
                  f"Severity confirmed: {sev}")
    update["findings"] = {"severity": sev}
    return update


def build_declare_subgraph(llm=None):
    g = StateGraph(IncidentState)
    g.add_node("intake", partial(_intake, llm=llm))
    g.add_node("severity", partial(_severity, llm=llm))
    g.add_edge(START, "intake")
    g.add_edge("intake", "severity")
    g.add_edge("severity", END)
    return g.compile()
