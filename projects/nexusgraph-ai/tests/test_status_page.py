from src.status_page import build_status_summary, incident_history, incident_updates


def test_status_summary_groups_streamflix_components():
    summary = build_status_summary()
    groups = {group["name"] for group in summary["groups"]}
    assert {"Streaming Experience", "Revenue Systems", "Identity", "Platform Operations"} <= groups
    assert summary["brand"] == "Streamflix Status"


def test_incident_history_contains_outage_lifecycle_statuses():
    history = incident_history()
    statuses = {item["status"] for item in history}
    assert {"Investigating", "Identified", "Monitoring", "Resolved"} <= statuses


def test_incident_updates_look_like_public_status_page_posts():
    updates = incident_updates("hist-1")
    assert updates
    assert {"timestamp", "status", "message"} <= set(updates[0])
    statuses = {update["status"] for update in updates}
    assert {"Investigating", "Identified", "Monitoring", "Resolved"} & statuses
