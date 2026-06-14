from src.incident.triage import build_triage_subgraph
from src.incident.graph_lookup import GraphContext
from src.incident.state import new_incident


def test_triage_records_findings_and_messages():
    state = new_incident("incident:playback-latency-sev1", "Playback Latency SEV1",
                         "SEV1", ["Playback Service"], "latency breach")
    out = build_triage_subgraph(llm=None, ctx=GraphContext(use_neo4j=False)).invoke(state)
    assert "impact" in out["findings"]
    assert "Playback Service" in out["findings"]["impact"]
    # owner/oncall keys always present (value may be None on CSV gaps)
    assert "owner" in out["findings"] and "oncall" in out["findings"]
    assert any(m["role"] == "triage" for m in out["slack_messages"])
