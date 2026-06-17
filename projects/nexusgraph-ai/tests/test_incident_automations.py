from src.incident.automations import execute_automation, select_automation


def test_select_automation_matches_severity_and_service():
    automation = select_automation("SEV1", ["playback-service"])
    assert automation["id"] == "fh:auto:sev1-streaming"
    assert "create_incident_channel" in automation["actions"]
    assert "post_status_update" in automation["actions"]


def test_select_automation_normalizes_human_service_name():
    automation = select_automation("sev1", ["Playback Service"])
    assert automation["id"] == "fh:auto:sev1-streaming"


def test_execute_automation_returns_simulated_incident_artifacts():
    automation = select_automation("SEV1", ["playback-service"])
    result = execute_automation(
        automation,
        incident_id="incident:playback-oom-sev1",
        title="Playback API OOMKilled SEV1",
    )
    assert result["channel"].startswith("#inc-")
    assert result["ticket"].startswith("INC-")
    assert any(task["action"] == "assign_roles" for task in result["timeline"])
    assert any(task["action"] == "generate_retro_summary" for task in result["timeline"])
