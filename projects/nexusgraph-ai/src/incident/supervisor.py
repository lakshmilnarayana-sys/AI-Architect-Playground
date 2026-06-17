from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
import time
import uuid

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


def _with_provenance(values: dict, thread_id: str, run_id: str, started_at: float) -> dict:
    final = dict(values)
    final["timeline"] = _dedupe_events(final.get("timeline", []))
    final["slack_messages"] = _dedupe_events(final.get("slack_messages", []), actor_key="author")
    final["observability"] = _dedupe_records(final.get("observability", []))
    final["logs"] = _dedupe_records(final.get("logs", []))
    final["_backend_provenance"] = {
        "run_id": run_id,
        "thread_id": thread_id,
        "executor": "LangGraph StateGraph",
        "checkpointer": "MemorySaver",
        "checkpointer_scope": "in_process_demo_only",
        "source": "stream_incident",
        "duration_kind": "backend_compute_seconds",
        "backend_compute_seconds": round(time.perf_counter() - started_at, 3),
        "approval_mode": "auto_approved_demo",
        "approval_note": "HITL gates are modeled in state/UI; stream_incident auto-approves them for deterministic demo playback.",
        "node_sequence": [
            "declare",
            "triage",
            "set_diagnose",
            "diagnose",
            "bump",
            "set_mitigate",
            "mitigate",
            "set_resolve",
            "resolve",
            "postmortem",
        ],
        "interrupt_before": ["set_mitigate", "set_resolve"],
    }
    return final


def _record_key(record: dict) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((str(key), str(value)) for key, value in record.items()))


def _dedupe_records(records: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for record in records:
        key = _record_key(record)
        if key in seen:
            continue
        seen.add(key)
        unique.append(record)
    return unique


def _event_key(event: dict, actor_key: str = "actor") -> tuple[str, str, str, str]:
    return (
        str(event.get("phase", "")),
        str(event.get(actor_key, "")),
        str(event.get("kind", "")),
        str(event.get("text", "")),
    )


def _dedupe_events(events: list[dict], actor_key: str = "actor",
                   seen: set[tuple[str, str, str, str]] | None = None) -> list[dict]:
    seen = seen if seen is not None else set()
    unique = []
    for event in events:
        key = _event_key(event, actor_key=actor_key)
        if key in seen:
            continue
        seen.add(key)
        unique.append(event)
    return unique


def stream_incident(state, llm=None, ctx=None, use_vector=True,
                    approve=None, thread_id="incident", on_final=None):
    """Yield (phase, new_messages) as the incident advances.

    ``approve(phase)`` is called at each HITL gate; returning False aborts the run.
    """
    approve = approve or (lambda phase: True)
    graph = build_incident_graph(llm=llm, ctx=ctx, use_vector=use_vector)
    cfg = {"configurable": {"thread_id": thread_id}}
    run_id = f"lg-{uuid.uuid4().hex[:12]}"
    started_at = time.perf_counter()
    emitted = 0
    seen_message_keys: set[tuple[str, str, str, str]] = set()

    def _drain():
        nonlocal emitted
        values = graph.get_state(cfg).values
        msgs = values.get("slack_messages", [])
        new = _dedupe_events(msgs[emitted:], actor_key="author", seen=seen_message_keys)
        emitted = len(msgs)
        return values.get("phase", ""), new

    graph.invoke(state, config=cfg)
    phase, new = _drain()
    if new:
        yield phase, new

    while graph.get_state(cfg).next:
        pending_phase = graph.get_state(cfg).values.get("phase", "")
        if not approve(pending_phase):
            if on_final:
                on_final(_with_provenance(graph.get_state(cfg).values, thread_id, run_id, started_at))
            return
        graph.invoke(None, config=cfg)
        phase, new = _drain()
        if new:
            yield phase, new
    if on_final:
        on_final(_with_provenance(graph.get_state(cfg).values, thread_id, run_id, started_at))
