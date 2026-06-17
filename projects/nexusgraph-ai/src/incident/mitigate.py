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
        "memory_leak": (
            "Shift traffic away from leaking pods, capture heap profiles, restart the worst "
            "offenders in batches, and roll back the build if RSS continues to climb."
        ),
        "node_pressure": (
            "Cordon pressure nodes, evict non-critical workloads, move affected replicas to "
            "healthy nodes, and verify node memory and disk pressure clear."
        ),
        "image_pull_backoff": (
            "Pin the last known-good image tag, validate registry credentials, restart image "
            "pulls, and pause the rollout until all pods leave ImagePullBackOff."
        ),
        "hpa_maxed": (
            "Raise HPA max replicas within capacity guardrails, shed low-priority traffic, "
            "scale dependent workers, and verify queue depth drains."
        ),
        "config_regression": (
            "Revert the changed config key through the config service, flush affected caches, "
            "and compare error rate against the pre-change baseline."
        ),
        "dependency_timeout": (
            "Fail over or bypass the timing-out dependency, raise circuit-breaker protection, "
            "reduce retry amplification, and confirm timeout rate recovers."
        ),
        "ingress_5xx": (
            "Drain unhealthy ingress upstreams, roll back the ingress rule change, rebalance "
            "traffic across zones, and verify 5xx rate returns below threshold."
        ),
        "network_packet_loss": (
            "Shift traffic out of the affected AZ, lower connection reuse pressure, engage "
            "network operations, and validate retransmits and packet loss normalize."
        ),
        "db_connection_pool_exhaustion": (
            "Temporarily raise pool limits, kill stuck sessions, reduce write concurrency, "
            "and verify pool wait queue and DB CPU recover."
        ),
        "kafka_consumer_lag": (
            "Scale consumers, pause non-critical producers, increase partition parallelism if "
            "safe, and track oldest lag until it drains."
        ),
        "redis_hot_key": (
            "Shard the hot key, enable local request coalescing, raise cache TTL for stable "
            "reads, and verify Redis p99 latency drops."
        ),
        "certificate_expiry": (
            "Rotate the expired certificate secret, restart mTLS clients in batches, validate "
            "handshakes, and add an expiry alert follow-up."
        ),
        "model_serving_errors": (
            "Roll back the model variant, route traffic to the stable endpoint, clear model "
            "cache, and verify inference error rate and p99 latency recover."
        ),
        "feature_store_stale": (
            "Switch to fallback features, replay the online-store writer lag, pause stale "
            "ranking experiments, and verify feature freshness."
        ),
        "log_pipeline_backpressure": (
            "Scale collectors, reduce verbose log sampling, drain buffers to the secondary "
            "sink, and verify dropped log percentage declines."
        ),
        "metrics_cardinality_explosion": (
            "Disable the high-cardinality metric label, reload scrape configs, compact the "
            "head block if needed, and verify active series growth stabilizes."
        ),
    }
    plan = plans.get(failure_mode)
    if not plan:
        plan = phrase(
            llm,
            f"Propose a concise mitigation plan for {_service(state)} following {rb_name}.",
            fallback=f"Proposed mitigation per {rb_name}: stabilize, fail over, verify recovery.",
        )
    update = emit("mitigate", "Remediation Agent", "mitigate", "action", plan)
    update["findings"] = {
        "mitigation_plan": plan,
        "remediation": {
            "service": _service(state),
            "runbook": runbook or {},
            "plan": plan,
            "status": "ready_for_commander_approval",
        },
    }
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
