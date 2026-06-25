"""Tests for the manual run CLI (src/incident/run.py)."""


def test_seed_from_alert_maps_labels():
    from src.incident.run import seed_from_alert
    alert = {"labels": {"alertname": "StreamFlixOOMKilled", "service": "billing-service",
                        "severity": "SEV2", "failure_mode": "oom_kill"}}
    state = seed_from_alert(alert)
    assert state["incident"]["affected_services"] == ["billing-service"]
    assert state["incident"]["severity"] == "SEV2"
    assert state["incident"]["failure_mode"] == "oom_kill"


def test_run_for_service_runs_pipeline(monkeypatch):
    # deterministic (INCIDENT_LIVE unset) — pipeline must complete and return timeline
    monkeypatch.delenv("INCIDENT_LIVE", raising=False)
    from src.incident.run import run_for_service
    final = run_for_service("billing-service", failure_mode="oom_kill", severity="SEV2")
    assert "timeline" in final and len(final["timeline"]) > 0


def test_service_from_labels_strips_pod_hash():
    from src.incident.run import _service_from_labels
    assert _service_from_labels({"pod": "billing-service-7d9f8c-abcde"}) == "billing-service"
    assert _service_from_labels({"service": "playback-service", "pod": "x-y-z"}) == "playback-service"
