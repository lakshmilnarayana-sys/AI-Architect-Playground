from functools import partial

from langgraph.graph import StateGraph, START, END

from src.incident.state import IncidentState
from src.incident.graph_lookup import GraphContext
from src.incident.agents import emit, phrase


def _service(state: IncidentState) -> str:
    services = state["incident"].get("affected_services") or ["the affected service"]
    return services[0]


def _planner(state: IncidentState, llm=None) -> dict:
    runbook = (state.get("findings") or {}).get("runbook")
    rb_name = runbook["name"] if runbook else "standard mitigation steps"
    plan = phrase(
        llm,
        f"Propose a concise mitigation plan for {_service(state)} following {rb_name}.",
        fallback=f"Proposed mitigation per {rb_name}: stabilize, fail over, verify recovery.",
    )
    update = emit("mitigate", "MitigationPlanner", "mitigate", "action", plan)
    update["findings"] = {"mitigation_plan": plan}
    return update


def _escalation(state: IncidentState, ctx: GraphContext) -> dict:
    svc = _service(state)
    sev = state["incident"].get("severity", "SEV3")
    policy = ctx.escalation_for(svc, sev)
    name = policy["name"] if policy else "no escalation policy mapped"
    update = emit("mitigate", "EscalationAgent", "mitigate", "action", f"Escalation policy: {name}")
    update["findings"] = {"escalation": policy}
    return update


def build_mitigate_subgraph(llm=None, ctx: GraphContext | None = None):
    ctx = ctx or GraphContext()
    g = StateGraph(IncidentState)
    g.add_node("planner", partial(_planner, llm=llm))
    g.add_node("escalation", partial(_escalation, ctx=ctx))
    g.add_edge(START, "planner")
    g.add_edge("planner", "escalation")
    g.add_edge("escalation", END)
    return g.compile()
