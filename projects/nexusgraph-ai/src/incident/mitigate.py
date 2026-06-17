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
    runtime = (state.get("findings") or {}).get("kubernetes_runtime", {})
    failure_mode = runtime.get("active_failure") or state["incident"].get("failure_mode")
    plans = {
        "oom_kill": (
            "Increase memory limit from 1024Mi to 1536Mi, roll one canary pod, "
            "drain OOMKilled pods, verify restart count stabilizes, then roll remaining replicas."
        ),
        "pod_restart": (
            "Pause rollout, inspect exit code 137, roll back the latest deployment if "
            "restarts continue, and page service owner."
        ),
        "disk_iops": (
            "Move hot cache path to provisioned IOPS storage, reduce cache compaction "
            "concurrency, and verify PVC latency under 50ms."
        ),
        "cpu_throttle": (
            "Raise CPU limit, reduce request fanout, enable HPA scale-out, and verify "
            "throttled ratio below 10%."
        ),
    }
    plan = plans.get(failure_mode)
    if not plan:
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
