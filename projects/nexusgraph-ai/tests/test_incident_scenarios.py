import pytest

from src.incident.scenarios import load_scenarios, get_scenario


def test_load_scenarios_returns_known_ids():
    scenarios = load_scenarios()
    ids = {s["id"] for s in scenarios}
    assert "playback-latency-sev1" in ids


def test_get_scenario_has_required_fields():
    s = get_scenario("playback-latency-sev1")
    assert s["severity"] == "SEV1"
    assert s["affected_services"] == ["Playback Service"]
    assert s["incident_id"].startswith("incident:")


def test_get_scenario_unknown_raises():
    with pytest.raises(KeyError):
        get_scenario("does-not-exist")
