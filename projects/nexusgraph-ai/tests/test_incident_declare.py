from src.incident.declare import build_declare_subgraph
from src.incident.state import new_incident


def test_declare_subgraph_emits_intake_and_severity():
    state = new_incident("incident:playback-latency-sev1", "Playback Latency SEV1",
                         "SEV1", ["Playback Service"], "latency breach")
    out = build_declare_subgraph(llm=None).invoke(state)
    texts = " ".join(e["text"] for e in out["timeline"])
    assert "SEV1" in texts
    assert out["findings"]["severity"] == "SEV1"
    assert out["phase"] == "declare"
    roles = {m["role"] for m in out["slack_messages"]}
    assert "bot" in roles
