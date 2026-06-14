from src.incident.diagnose import build_diagnose_subgraph
from src.incident.graph_lookup import GraphContext
from src.incident.state import new_incident


def test_diagnose_matches_runbook_and_sets_rca():
    state = new_incident("incident:playback-latency-sev1", "Playback Latency SEV1",
                         "SEV1", ["Playback Service"], "p99 latency breach on CDN")
    out = build_diagnose_subgraph(llm=None, ctx=GraphContext(use_neo4j=False),
                                  use_vector=False).invoke(state)
    assert out["findings"]["runbook"] is not None
    assert "playback" in out["findings"]["runbook"]["id"].lower()
    assert out["findings"]["rca"]            # non-empty hypothesis
    assert any(m["role"] == "diagnose" for m in out["slack_messages"])
