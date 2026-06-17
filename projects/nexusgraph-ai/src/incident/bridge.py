from __future__ import annotations


def collect_zoom_actions(incident: dict, findings: dict) -> dict:
    """Simulate extracting action items from an incident bridge transcript."""
    service = (incident.get("affected_services") or ["affected service"])[0]
    failure_mode = incident.get("failure_mode") or "service degradation"
    oncall = findings.get("oncall") or {}
    commander = (findings.get("incident_commander") or {}).get("name", "Incident Commander")
    return {
        "bridge": f"zoom://streamflix/{incident.get('id', 'incident').replace(':', '-')}",
        "transcript_source": "simulated Zoom bridge transcript",
        "participants": [
            commander,
            oncall.get("name", "Primary on-call engineer"),
            "Incident observer",
            "Support communications lead",
        ],
        "action_items": [
            f"{oncall.get('name', 'On-call engineer')} to apply remediation for {failure_mode} on {service}.",
            "Scribe Agent to publish approved customer status updates.",
            "Incident Commander Agent to verify mitigation and close the loop.",
        ],
    }
