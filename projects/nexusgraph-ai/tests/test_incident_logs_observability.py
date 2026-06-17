from src.incident.logs import get_logs_for_incident
from src.incident.observability import (
    external_recommendations,
    get_observability_evidence,
)


def test_get_logs_for_incident_filters_by_scenario_and_service():
    logs = get_logs_for_incident("playback-oom-sev1", "playback-service")
    assert logs
    assert all(log["scenario_id"] == "playback-oom-sev1" for log in logs)
    assert any("OOMKilled" in log["message"] for log in logs)


def test_get_logs_for_incident_filters_by_severity():
    logs = get_logs_for_incident("playback-oom-sev1", "playback-service", severity="ERROR")
    assert logs
    assert all(log["severity"] == "ERROR" for log in logs)


def test_get_logs_for_incident_falls_back_to_scenario_logs_for_inferred_service_gap():
    logs = get_logs_for_incident("playback-oom-sev1", "billing-service")
    assert logs
    assert all(log.get("fallback_match") is True for log in logs)


def test_observability_evidence_includes_dashboards_alerts_and_traces():
    evidence = get_observability_evidence("playback-service", "oom_kill")
    kinds = {item["kind"] for item in evidence}
    assert {"dashboard", "alert", "trace"} <= kinds
    keys = {(item.get("kind"), item.get("name"), item.get("query")) for item in evidence}
    assert len(keys) == len(evidence)


def test_external_recommendations_include_logging_and_observability():
    recommendations = external_recommendations()
    names = {item["name"] for item in recommendations}
    assert "OpenSearch" in names
    assert "Grafana Cloud" in names
