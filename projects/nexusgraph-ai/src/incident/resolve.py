from langgraph.graph import StateGraph, START, END

from src.incident.state import IncidentState
from src.incident.agents import emit


def _verify(state: IncidentState) -> dict:
    recovered = bool(state["incident"].get("recovered", True))
    svc = (state["incident"].get("affected_services") or ["service"])[0]
    runtime = dict(state.get("runtime") or {})
    if recovered and runtime:
        runtime["health"] = "healthy"
        runtime["pod_status"] = "Running"
        runtime["restart_count_delta"] = 0
    text = (f"SLO verification: {svc} recovered within target."
            if recovered else
            f"SLO verification: {svc} has NOT recovered — recommend re-diagnose.")
    update = emit("resolve", "SLOVerification", "resolve", "finding", text)
    update["findings"] = {"slo_recovered": recovered}
    if runtime:
        update["findings"]["recovery_runtime"] = runtime
        update["runtime"] = runtime
    return update


def _closeout(state: IncidentState) -> dict:
    if not state["incident"].get("recovered", True):
        return emit("resolve", "Incident Commander", "commander", "message",
                    "Holding resolution — looping back to diagnosis.")
    return emit("resolve", "Incident Commander", "commander", "message",
                "Incident mitigated and verified; moving to postmortem.")


def build_resolve_subgraph(llm=None):
    g = StateGraph(IncidentState)
    g.add_node("verify", _verify)
    g.add_node("closeout", _closeout)
    g.add_edge(START, "verify")
    g.add_edge("verify", "closeout")
    g.add_edge("closeout", END)
    return g.compile()
