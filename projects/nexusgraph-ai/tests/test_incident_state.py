from src.incident.state import new_incident, merge_findings


def test_new_incident_seeds_core_fields():
    state = new_incident(
        incident_id="incident:playback-latency-sev1",
        title="Playback Latency SEV1",
        severity="SEV1",
        affected_services=["Playback Service"],
        signal="latency breach",
    )
    assert state["phase"] == "declare"
    assert state["incident"]["severity"] == "SEV1"
    assert state["timeline"] == []
    assert state["slack_messages"] == []
    assert state["findings"] == {}


def test_merge_findings_is_shallow_update():
    merged = merge_findings({"owner": "A"}, {"oncall": "B"})
    assert merged == {"owner": "A", "oncall": "B"}


def test_merge_findings_overwrites_key():
    assert merge_findings({"severity": "SEV2"}, {"severity": "SEV1"})["severity"] == "SEV1"
