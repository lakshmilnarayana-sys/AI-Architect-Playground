from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(name: str):
    return yaml.safe_load((ROOT / "data" / name).read_text()) or []


def test_runbooks_have_domain_specific_steps_and_signals():
    runbooks = load_yaml("runbooks.yaml")
    playback = next(r for r in runbooks if r["id"] == "runbook:playback-latency")

    assert "steps" in playback and len(playback["steps"]) >= 5
    assert any("kubectl" in step["command"] for step in playback["steps"])
    assert any(
        "CDN" in step["description"] or "manifest" in step["description"]
        for step in playback["steps"]
    )
    assert "rollback_criteria" in playback
    assert "observability_checks" in playback


def test_kubernetes_resources_model_failure_modes_as_key_value_pairs():
    resources = load_yaml("kubernetes_resources.yaml")
    playback = next(r for r in resources if r["service"] == "playback-service")

    assert playback["namespace"] == "streamflix-prod"
    assert playback["resources"]["limits"]["memory"] == "1024Mi"
    assert "oom_kill" in playback["failure_modes"]
    assert "cpu_throttle" in playback["failure_modes"]
    assert len({mode for r in resources for mode in r["failure_modes"]}) >= 16
    assert "dependency_timeout" in playback["failure_modes"]
    assert "ingress_5xx" in playback["failure_modes"]
    assert playback["failure_modes"]["oom_kill"]["symptom"] == "OOMKilled"


def test_scripted_scenarios_cover_expanded_failure_modes():
    scenarios = load_yaml("incident_scenarios.yaml")
    modes = {scenario.get("failure_mode") for scenario in scenarios if scenario.get("failure_mode")}

    assert len(modes) >= 16
    assert {"certificate_expiry", "model_serving_errors", "metrics_cardinality_explosion"} <= modes


def test_logs_and_observability_sources_cover_outage_scenarios():
    logs = load_yaml("service_logs.yaml")
    obs = load_yaml("observability_sources.yaml")

    assert any(
        l["scenario_id"] == "playback-oom-sev1" and "OOMKilled" in l["message"]
        for l in logs
    )
    assert any(
        o["kind"] == "external_logging" and "OpenSearch" in o["recommendation"]
        for o in obs
    )
    assert any(
        o["kind"] == "observability" and "Grafana" in o["recommendation"]
        for o in obs
    )


def test_firehydrant_style_automations_cover_critical_incident_workflow():
    automations = load_yaml("firehydrant_runbook_automations.yaml")
    actions = {action for item in automations for action in item["actions"]}

    assert {"create_incident_channel", "create_tracking_ticket", "assign_roles"} <= actions
    assert {"post_status_update", "notify_stakeholders", "capture_timeline"} <= actions
    assert {"assign_tasks", "escalate_by_severity", "generate_retro_summary"} <= actions
