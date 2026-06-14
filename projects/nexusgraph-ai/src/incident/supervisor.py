from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from src.incident.state import IncidentState
from src.incident.graph_lookup import GraphContext
from src.incident.declare import build_declare_subgraph
from src.incident.triage import build_triage_subgraph
from src.incident.diagnose import build_diagnose_subgraph
from src.incident.mitigate import build_mitigate_subgraph
from src.incident.resolve import build_resolve_subgraph
from src.incident.postmortem import build_postmortem_subgraph

MAX_REDIAGNOSE = 2  # loop-back guard so a never-recovering scenario still terminates


def _phase_setter(name: str):
    def _set(state: IncidentState) -> dict:
        return {"phase": name}
    return _set


def _route_after_resolve(state: IncidentState) -> str:
    findings = state.get("findings") or {}
    attempts = (state.get("incident") or {}).get("_diagnose_attempts", 0)
    if not findings.get("slo_recovered", True) and attempts < MAX_REDIAGNOSE:
        return "rediagnose"
    return "postmortem"


def _bump_attempts(state: IncidentState) -> dict:
    inc = dict(state.get("incident") or {})
    inc["_diagnose_attempts"] = inc.get("_diagnose_attempts", 0) + 1
    return {"incident": inc}


def build_incident_graph(llm=None, ctx: GraphContext | None = None, use_vector: bool = True):
    ctx = ctx or GraphContext()
    g = StateGraph(IncidentState)

    g.add_node("declare", build_declare_subgraph(llm=llm))
    g.add_node("triage", build_triage_subgraph(llm=llm, ctx=ctx))
    g.add_node("set_diagnose", _phase_setter("diagnose"))
    g.add_node("diagnose", build_diagnose_subgraph(llm=llm, ctx=ctx, use_vector=use_vector))
    g.add_node("bump", _bump_attempts)
    g.add_node("set_mitigate", _phase_setter("mitigate"))
    g.add_node("mitigate", build_mitigate_subgraph(llm=llm, ctx=ctx))
    g.add_node("set_resolve", _phase_setter("resolve"))
    g.add_node("resolve", build_resolve_subgraph(llm=llm))
    g.add_node("postmortem", build_postmortem_subgraph(llm=llm))

    g.add_edge(START, "declare")
    g.add_edge("declare", "triage")
    g.add_edge("triage", "set_diagnose")
    g.add_edge("set_diagnose", "diagnose")
    g.add_edge("diagnose", "bump")
    g.add_edge("bump", "set_mitigate")
    g.add_edge("set_mitigate", "mitigate")
    g.add_edge("mitigate", "set_resolve")
    g.add_edge("set_resolve", "resolve")
    g.add_conditional_edges("resolve", _route_after_resolve,
                            {"rediagnose": "set_diagnose", "postmortem": "postmortem"})
    g.add_edge("postmortem", END)

    return g.compile(checkpointer=MemorySaver(),
                     interrupt_before=["set_mitigate", "set_resolve"])


def run_incident(state: IncidentState, llm=None, ctx: GraphContext | None = None,
                 use_vector: bool = True, thread_id: str = "incident"):
    """Run to completion, auto-approving HITL gates. Returns the final state values."""
    graph = build_incident_graph(llm=llm, ctx=ctx, use_vector=use_vector)
    cfg = {"configurable": {"thread_id": thread_id}}
    graph.invoke(state, config=cfg)
    while graph.get_state(cfg).next:
        graph.invoke(None, config=cfg)
    return graph.get_state(cfg).values


def stream_incident(state, llm=None, ctx=None, use_vector=True,
                    approve=None, thread_id="incident"):
    """Yield (phase, new_messages) as the incident advances.

    ``approve(phase)`` is called at each HITL gate; returning False aborts the run.
    """
    approve = approve or (lambda phase: True)
    graph = build_incident_graph(llm=llm, ctx=ctx, use_vector=use_vector)
    cfg = {"configurable": {"thread_id": thread_id}}
    emitted = 0

    def _drain():
        nonlocal emitted
        values = graph.get_state(cfg).values
        msgs = values.get("slack_messages", [])
        new = msgs[emitted:]
        emitted = len(msgs)
        return values.get("phase", ""), new

    graph.invoke(state, config=cfg)
    phase, new = _drain()
    if new:
        yield phase, new

    while graph.get_state(cfg).next:
        pending_phase = graph.get_state(cfg).values.get("phase", "")
        if not approve(pending_phase):
            return
        graph.invoke(None, config=cfg)
        phase, new = _drain()
        if new:
            yield phase, new
