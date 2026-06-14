from src.incident.supervisor import build_incident_graph
from src.incident.graph_lookup import GraphContext
from src.incident.state import new_incident

CTX = GraphContext(use_neo4j=False)


def _run_to_completion(state, config):
    graph = build_incident_graph(llm=None, ctx=CTX, use_vector=False)
    graph.invoke(state, config=config)
    while graph.get_state(config).next:
        graph.invoke(None, config=config)
    return graph.get_state(config).values


def test_happy_path_reaches_postmortem():
    state = new_incident("incident:playback-latency-sev1", "Playback Latency SEV1",
                         "SEV1", ["Playback Service"], "latency breach")
    state["incident"]["recovered"] = True
    cfg = {"configurable": {"thread_id": "t1"}}
    values = _run_to_completion(state, cfg)
    assert values["findings"]["postmortem_md"]
    phases = [e["phase"] for e in values["timeline"]]
    assert "postmortem" in phases


def test_failed_slo_loops_back_to_diagnose():
    state = new_incident("incident:playback-latency-sev1", "Playback Latency SEV1",
                         "SEV1", ["Playback Service"], "latency breach")
    state["incident"]["recovered"] = False
    cfg = {"configurable": {"thread_id": "t2"}}
    values = _run_to_completion(state, cfg)
    diagnose_runs = sum(1 for e in values["timeline"]
                        if e["phase"] == "diagnose" and e["actor"] == "EvidenceAgent")
    assert diagnose_runs >= 2  # initial + at least one loop-back


def test_hitl_interrupts_before_mitigate():
    state = new_incident("incident:playback-latency-sev1", "Playback Latency SEV1",
                         "SEV1", ["Playback Service"], "latency breach")
    state["incident"]["recovered"] = True
    cfg = {"configurable": {"thread_id": "t3"}}
    graph = build_incident_graph(llm=None, ctx=CTX, use_vector=False)
    graph.invoke(state, config=cfg)
    assert graph.get_state(cfg).next  # paused at an interrupt before mitigate
