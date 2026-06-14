from functools import partial

from langgraph.graph import StateGraph, START, END

from src.incident.state import IncidentState
from src.incident.graph_lookup import GraphContext
from src.incident.agents import emit, phrase


def _service(state: IncidentState) -> str:
    services = state["incident"].get("affected_services") or ["the affected service"]
    return services[0]


def _runbook(state: IncidentState, ctx: GraphContext) -> dict:
    svc = _service(state)
    matches = ctx.runbooks_for(svc)
    chosen = matches[0] if matches else None
    name = chosen["name"] if chosen else "no matching runbook"
    update = emit("diagnose", "DiagnoseAgent", "diagnose", "finding", f"Runbook matched: {name}")
    update["findings"] = {"runbook": chosen}
    return update


def _rca(state: IncidentState, llm=None) -> dict:
    signal = state["incident"].get("signal", "")
    svc = _service(state)
    hypothesis = phrase(
        llm,
        f"Give a one-line root-cause hypothesis for {svc} given: {signal}",
        fallback=f"Leading hypothesis: degradation in {svc} consistent with '{signal}'.",
    )
    update = emit("diagnose", "DiagnoseAgent", "diagnose", "finding", hypothesis)
    update["findings"] = {"rca": hypothesis}
    return update


def _evidence(state: IncidentState, use_vector: bool) -> dict:
    snippet = "Vector evidence skipped"
    if use_vector:
        try:
            from src.vector_query import query_vector_store
            res = query_vector_store(state["incident"].get("signal", ""))
            matches = res.get("matches", [])
            snippet = f"Retrieved {len(matches)} supporting document(s)."
        except Exception as exc:
            snippet = f"Vector evidence unavailable ({type(exc).__name__})."
    return emit("diagnose", "EvidenceAgent", "diagnose", "action", snippet)


def build_diagnose_subgraph(llm=None, ctx: GraphContext | None = None, use_vector: bool = True):
    ctx = ctx or GraphContext()
    g = StateGraph(IncidentState)
    g.add_node("runbook", partial(_runbook, ctx=ctx))
    g.add_node("rca", partial(_rca, llm=llm))
    g.add_node("evidence", partial(_evidence, use_vector=use_vector))
    g.add_edge(START, "runbook")
    g.add_edge("runbook", "rca")
    g.add_edge("rca", "evidence")
    g.add_edge("evidence", END)
    return g.compile()
