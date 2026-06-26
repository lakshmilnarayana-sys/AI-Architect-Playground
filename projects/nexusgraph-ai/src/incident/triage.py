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


def _kubernetes_context(state: IncidentState) -> dict:
    from src.incident.kubernetes import clear_failure, get_service_resource, inject_failure

    svc = _primary_service(state)
    try:
        resource = get_service_resource(svc)
    except KeyError:
        signal = f"{state['incident'].get('title', '')} {state['incident'].get('signal', '')}".lower()
        fallback_service = "billing-service" if "billing" in signal else "playback-service"
        resource = get_service_resource(fallback_service)
        svc = fallback_service
    from src.incident.kubernetes import live_runtime
    failure_mode = state["incident"].get("failure_mode")
    simulate = bool(state["incident"].get("simulate_failure"))
    runtime = live_runtime(svc) or (
        inject_failure(resource, failure_mode)
        if simulate and failure_mode
        else clear_failure(resource)
    )
    update = emit(
        "triage",
        "KubernetesAgent",
        "triage",
        "finding",
        (
            f"Kubernetes context: {resource['cluster']}/{resource['namespace']} "
            f"{resource['workload']['name']} status={runtime['pod_status']}"
        ),
    )
    update["findings"] = {
        "kubernetes_resource": resource,
        "kubernetes_runtime": runtime,
    }
    update["runtime"] = runtime
    return update


def _automation_kickoff(state: IncidentState) -> dict:
    from src.incident.automations import execute_automation, select_automation

    incident = state["incident"]
    findings = state.get("findings") or {}
    try:
        automation = select_automation(
            incident.get("severity", "SEV3"),
            incident.get("affected_services", []),
        )
    except KeyError:
        return emit(
            "triage",
            "RunbookAutomationAgent",
            "commander",
            "action",
            "No FireHydrant-style automation matched this incident.",
        )
    result = execute_automation(
        automation,
        incident_id=incident["id"],
        title=incident["title"],
    )
    oncall = findings.get("oncall") or {}
    owner = findings.get("owner") or {}
    commander = findings.get("incident_commander") or {"name": "Incident Commander Agent"}
    slack_channel = {
        "channel": result["channel"],
        "details": f"{incident['severity']} {incident['title']}",
        "oncall_engineers": [oncall.get("name", "Primary on-call engineer")],
        "incident_commanders": [commander.get("name", "Incident Commander Agent")],
        "incident_observers": [
            "Scribe Agent",
            "Support Communications Observer",
            owner.get("name", "Service owner observer"),
        ],
    }
    update = emit(
        "triage",
        "FireHydrant Runbook Automation",
        "commander",
        "action",
        (
            f"Incident Commander triggered the Incident Management runbook; "
            f"FireHydrant created Slack channel {result['channel']} with incident details, "
            f"on-call engineers, incident commanders, and incident observers, and "
            f"tracking ticket {result['ticket']} opened."
        ),
    )
    result["slack_channel"] = slack_channel
    update["findings"] = {"automation": result, "slack_channel": slack_channel}
    return update


def _incident_bridge(state: IncidentState) -> dict:
    """Open the Zoom incident bridge and pull responders in — part of the commander's
    plumbing setup, immediately after FireHydrant creates the Slack channel."""
    from src.incident.bridge import collect_zoom_actions

    bridge = collect_zoom_actions(state["incident"], state.get("findings") or {})
    update = emit(
        "triage",
        "Zoom Bridge Agent",
        "commander",
        "action",
        (
            f"Opened Zoom incident bridge and pulled {len(bridge['participants'])} responders in; "
            f"{len(bridge['action_items'])} action item(s) captured."
        ),
    )
    update["findings"] = {"zoom_bridge": bridge}
    return update


def build_triage_subgraph(llm=None, ctx: GraphContext | None = None):
    ctx = ctx or GraphContext()
    g = StateGraph(IncidentState)
    g.add_node("ownership", partial(_ownership, ctx=ctx))
    g.add_node("oncall", partial(_oncall, ctx=ctx))
    g.add_node("automation_kickoff", _automation_kickoff)
    g.add_node("incident_bridge", _incident_bridge)
    g.add_node("impact", partial(_impact, ctx=ctx))
    g.add_node("kubernetes_context", _kubernetes_context)
    # Command sequence: identify owner + on-call → FireHydrant spins up the Slack channel
    # and pages on-call → open the Zoom bridge and pull responders in → then the rest
    # of triage (blast radius, live Kubernetes context).
    g.add_edge(START, "ownership")
    g.add_edge("ownership", "oncall")
    g.add_edge("oncall", "automation_kickoff")
    g.add_edge("automation_kickoff", "incident_bridge")
    g.add_edge("incident_bridge", "impact")
    g.add_edge("impact", "kubernetes_context")
    g.add_edge("kubernetes_context", END)
    return g.compile()
