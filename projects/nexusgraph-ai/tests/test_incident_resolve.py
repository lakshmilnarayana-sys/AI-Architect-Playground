from src.incident.resolve import build_resolve_subgraph
from src.incident.state import new_incident


def _state(recovered=True):
    s = new_incident("incident:playback-latency-sev1", "Playback Latency SEV1",
                     "SEV1", ["Playback Service"], "latency breach")
    s["incident"]["recovered"] = recovered
    return s


def test_resolve_marks_recovered_true():
    out = build_resolve_subgraph(llm=None).invoke(_state(True))
    assert out["findings"]["slo_recovered"] is True


def test_resolve_marks_recovered_false():
    out = build_resolve_subgraph(llm=None).invoke(_state(False))
    assert out["findings"]["slo_recovered"] is False
    assert any("not recovered" in m["text"].lower() for m in out["slack_messages"])
