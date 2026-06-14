from functools import partial

from langgraph.graph import StateGraph, START, END

from src.incident.state import IncidentState
from src.incident.graph_lookup import GraphContext
from src.incident.agents import emit


def _primary_service(state: IncidentState) -> str:
    services = state["incident"].get("affected_services") or ["the affected service"]
    return services[0]


def _ownership(state: IncidentState, ctx: GraphContext) -> dict:
    svc = _primary_service(state)
    owner = ctx.owner_for(svc)
    name = owner["name"] if owner else "unmapped owner"
    update = emit("triage", "TriageAgent", "triage", "finding", f"Owner of {svc}: {name}")
    update["findings"] = {"owner": owner}
    return update


def _oncall(state: IncidentState, ctx: GraphContext) -> dict:
    svc = _primary_service(state)
    oncall = ctx.oncall_for(svc)
    name = oncall["name"] if oncall else "no on-call mapped"
    update = emit("triage", "TriageAgent", "oncall", "action", f"Paging on-call for {svc}: {name}")
    update["findings"] = {"oncall": oncall}
    return update


def _impact(state: IncidentState, ctx: GraphContext) -> dict:
    services = state["incident"].get("affected_services") or []
    blast = ", ".join(services) or "scope under assessment"
    update = emit("triage", "TriageAgent", "triage", "finding", f"Impact / blast radius: {blast}")
    update["findings"] = {"impact": services}
    return update


def build_triage_subgraph(llm=None, ctx: GraphContext | None = None):
    ctx = ctx or GraphContext()
    g = StateGraph(IncidentState)
    g.add_node("ownership", partial(_ownership, ctx=ctx))
    g.add_node("oncall", partial(_oncall, ctx=ctx))
    g.add_node("impact", partial(_impact, ctx=ctx))
    g.add_edge(START, "ownership")
    g.add_edge("ownership", "oncall")
    g.add_edge("oncall", "impact")
    g.add_edge("impact", END)
    return g.compile()
