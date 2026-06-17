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
    update = emit(
        "diagnose",
        "Remediation Agent",
        "diagnose",
        "finding",
        f"Pulled service runbook for {svc}: {name}",
    )
    update["findings"] = {"runbook": chosen}
    return update


def _rca(state: IncidentState, llm=None) -> dict:
    signal = state["incident"].get("signal", "")
    svc = _service(state)
    runtime = (state.get("findings") or {}).get("kubernetes_runtime", {})
    failure = runtime.get("active_failure")
    hypothesis = phrase(
        llm,
        f"Give a one-line root-cause hypothesis for {svc} given: {signal}",
        fallback=(
            f"Leading hypothesis: {failure} in {svc} is consistent with '{signal}'."
            if failure
            else f"Leading hypothesis: degradation in {svc} consistent with '{signal}'."
        ),
    )
    update = emit("diagnose", "DiagnoseAgent", "diagnose", "finding", hypothesis)
    update["findings"] = {"rca": hypothesis}
    return update


def _logs(state: IncidentState) -> dict:
    from src.incident.logs import get_logs_for_incident

    incident = state["incident"]
    scenario_id = incident.get("scenario_id") or incident.get("id", "").split("incident:")[-1]
    logs = get_logs_for_incident(scenario_id, _service(state))
    text = (
        f"Static production logs: retrieved {len(logs)} log line(s) for {scenario_id}."
        if logs
        else f"Static production logs: no matching log lines for {scenario_id}."
    )
    update = emit("diagnose", "LogEvidenceAgent", "diagnose", "action", text)
    update["logs"] = logs
    update["findings"] = {"logs": logs}
    return update


def _observability(state: IncidentState) -> dict:
    from src.incident.observability import get_observability_evidence

    runtime = (state.get("findings") or {}).get("kubernetes_runtime", {})
    failure_mode = runtime.get("active_failure") or state["incident"].get("failure_mode") or "unknown"
    evidence = get_observability_evidence(_service(state), failure_mode)
    update = emit(
        "diagnose",
        "ObservabilityAgent",
        "diagnose",
        "action",
        f"Observability evidence: selected {len(evidence)} dashboard/alert/trace item(s).",
    )
    update["observability"] = evidence
    update["findings"] = {"observability": evidence}
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


def _zoom_bridge(state: IncidentState) -> dict:
    from src.incident.bridge import collect_zoom_actions

    bridge = collect_zoom_actions(state["incident"], state.get("findings") or {})
    update = emit(
        "diagnose",
        "Zoom Agent",
        "diagnose",
        "action",
        f"Collected {len(bridge['action_items'])} action item(s) from the incident bridge.",
    )
    update["findings"] = {"zoom_bridge": bridge}
    return update


def build_diagnose_subgraph(llm=None, ctx: GraphContext | None = None, use_vector: bool = True):
    ctx = ctx or GraphContext()
    g = StateGraph(IncidentState)
    g.add_node("runbook", partial(_runbook, ctx=ctx))
    g.add_node("rca", partial(_rca, llm=llm))
    g.add_node("logs", _logs)
    g.add_node("observability", _observability)
    g.add_node("evidence", partial(_evidence, use_vector=use_vector))
    g.add_node("zoom_bridge", _zoom_bridge)
    g.add_edge(START, "runbook")
    g.add_edge("runbook", "rca")
    g.add_edge("rca", "logs")
    g.add_edge("logs", "observability")
    g.add_edge("observability", "evidence")
    g.add_edge("evidence", "zoom_bridge")
    g.add_edge("zoom_bridge", END)
    return g.compile()
