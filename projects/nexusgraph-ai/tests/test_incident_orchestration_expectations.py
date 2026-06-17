from src.incident.graph_lookup import GraphContext
from src.incident.jira import query_incident_metrics, save_incident, set_store_path
from src.incident.state import new_incident
from src.incident.supervisor import run_incident


def _oom_state():
    state = new_incident(
        "incident:playback-oom-orchestration",
        "Playback API OOMKilled SEV1",
        "SEV1",
        ["playback-service"],
        "p99 playback start latency above 2500ms and OOMKilled pods above threshold.",
    )
    state["incident"]["scenario_id"] = "playback-oom-sev1"
    state["incident"]["simulate_failure"] = True
    state["incident"]["failure_mode"] = "oom_kill"
    state["incident"]["recovered"] = True
    return state


def test_observability_alert_drives_incident_declaration_and_orchestration():
    final = run_incident(
        _oom_state(),
        ctx=GraphContext(use_neo4j=False),
        use_vector=False,
        thread_id="orchestration-alert",
    )
    findings = final["findings"]

    assert findings["alert"]["triggered"] is True
    assert "threshold" in findings["alert"]["reason"].lower()
    assert findings["incident_commander"]["role"] == "primary_orchestrator"
    assert findings["slack_channel"]["channel"].startswith("#inc-")
    assert findings["slack_channel"]["oncall_engineers"]
    assert findings["slack_channel"]["incident_commanders"]
    assert findings["slack_channel"]["incident_observers"]


def test_remediation_scribe_zoom_and_status_updates_are_modeled():
    final = run_incident(
        _oom_state(),
        ctx=GraphContext(use_neo4j=False),
        use_vector=False,
        thread_id="orchestration-scribe",
    )
    findings = final["findings"]

    assert findings["remediation"]["runbook"]["id"].startswith("runbook:")
    assert "increase memory limit" in findings["remediation"]["plan"].lower()
    assert findings["zoom_bridge"]["action_items"]
    assert findings["scribe_summary"]["timeline"]
    assert findings["status_update"]["requires_human_approval"] is True
    assert findings["status_update"]["targets"] == ["slack", "status_page"]
    assert final["approvals"]["status_update"]["required"] is True
    assert final["status_page"]["pending_update"]


def test_jira_simulation_saves_incident_and_queries_metrics(tmp_path):
    store = tmp_path / "jira.yaml"
    set_store_path(store)
    final = run_incident(
        _oom_state(),
        ctx=GraphContext(use_neo4j=False),
        use_vector=False,
        thread_id="orchestration-jira",
    )

    saved = save_incident(final)
    metrics = query_incident_metrics()

    assert saved["key"].startswith("INC-")
    assert metrics["total_incidents"] >= 1
    assert metrics["by_severity"]["SEV1"] >= 1
    assert metrics["by_service"]["playback-service"] >= 1
    assert metrics["mean_time_to_mitigate_minutes"] >= 0


def test_operator_mode_unmapped_service_falls_back_to_modeled_kubernetes_resource():
    state = new_incident(
        "incident:operator-billing",
        "Operator reported disk IOPS saturation",
        "SEV1",
        [],
        "Max Disk IOPS limit hit consecutively for an hour on Billing Service.",
    )
    state["incident"]["simulate_failure"] = True
    state["incident"]["failure_mode"] = "disk_iops"
    state["incident"]["recovered"] = True

    final = run_incident(
        state,
        ctx=GraphContext(use_neo4j=False),
        use_vector=False,
        thread_id="operator-fallback",
    )

    assert final["findings"]["kubernetes_runtime"]["service"] == "billing-service"
    assert final["findings"]["kubernetes_runtime"]["pod_status"] == "DiskIOPSSaturation"
