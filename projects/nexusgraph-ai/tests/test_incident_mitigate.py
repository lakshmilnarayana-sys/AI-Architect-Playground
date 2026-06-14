from src.incident.mitigate import build_mitigate_subgraph
from src.incident.graph_lookup import GraphContext
from src.incident.state import new_incident


def test_mitigate_sets_plan_and_escalation():
    state = new_incident("incident:playback-latency-sev1", "Playback Latency SEV1",
                         "SEV1", ["Playback Service"], "latency breach")
    state["findings"] = {"runbook": {"id": "runbook:playback-latency", "name": "Playback Latency Runbook"}}
    out = build_mitigate_subgraph(llm=None, ctx=GraphContext(use_neo4j=False)).invoke(state)
    assert out["findings"]["mitigation_plan"]
    assert out["findings"]["escalation"] is not None
    assert any(m["role"] == "mitigate" for m in out["slack_messages"])
