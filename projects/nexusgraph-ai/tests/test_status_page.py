from src.status_page import build_status_summary, incident_history


def test_status_summary_groups_streamflix_components():
    summary = build_status_summary()
    groups = {group["name"] for group in summary["groups"]}
    assert {"Streaming Experience", "Revenue Systems", "Identity", "Platform Operations"} <= groups
    assert summary["brand"] == "Streamflix Status"


def test_incident_history_contains_outage_lifecycle_statuses():
    history = incident_history()
    statuses = {item["status"] for item in history}
    assert {"Investigating", "Identified", "Monitoring", "Resolved"} <= statuses
