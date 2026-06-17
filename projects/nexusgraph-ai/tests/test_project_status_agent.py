import pytest

from src.project_status.supervisor import run_project_status


def test_project_status_agent_produces_weekly_report_with_risks_and_blockers():
    report = run_project_status("Playback Resiliency 2026")

    assert report["project"] == "Playback Resiliency 2026"
    assert report["overall_status"] in {"Green", "Yellow", "Red"}
    assert report["risks"]
    assert report["blockers"]
    assert report["dependencies"]
    assert "executive_summary" in report
    assert "next_actions" in report
    assert any("week_over_week" in item for item in report["insights"])


def test_project_status_agent_tracks_memory_across_snapshots():
    report = run_project_status("Observability Unification")

    assert any("week_over_week" in item for item in report["insights"])
    assert report["overall_status"] == "Yellow"
    assert "OpenTelemetry rollout" in report["executive_summary"]


def test_project_status_agent_is_deterministic_for_same_project():
    first = run_project_status("Billing Platform Modernization")
    second = run_project_status("Billing Platform Modernization")

    assert first == second
    assert first["overall_status"] == "Red"
    assert first["next_actions"]


def test_project_status_agent_raises_for_unknown_project():
    with pytest.raises(KeyError, match="Unknown project"):
        run_project_status("Unknown Project")
