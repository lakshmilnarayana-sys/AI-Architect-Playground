from src.incident.postmortem import build_postmortem_subgraph
from src.incident.state import new_incident


def test_postmortem_emits_markdown_and_actions():
    state = new_incident("incident:playback-latency-sev1", "Playback Latency SEV1",
                         "SEV1", ["Playback Service"], "latency breach")
    state["timeline"] = [{"ts": "10:00:00", "phase": "declare", "actor": "Incident Bot",
                          "role": "bot", "kind": "message", "text": "SEV1 declared", "details": {}}]
    out = build_postmortem_subgraph(llm=None).invoke(state)
    md = out["findings"]["postmortem_md"]
    assert "# Postmortem" in md
    assert "Playback Latency SEV1" in md
    assert out["findings"]["action_items"]
