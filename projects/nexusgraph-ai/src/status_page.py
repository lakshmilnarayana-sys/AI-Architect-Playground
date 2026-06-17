from __future__ import annotations

from src.incident.scenarios import load_scenarios


def build_status_summary() -> dict:
    return {
        "brand": "Streamflix Status",
        "headline": "Service status and incident history for Streamflix production systems.",
        "groups": [
            {
                "name": "Streaming Experience",
                "components": ["playback-service", "manifest-service", "cdn-routing-service"],
                "uptime": "99.93%",
            },
            {
                "name": "Revenue Systems",
                "components": ["billing-service", "payment-gateway-service"],
                "uptime": "99.95%",
            },
            {
                "name": "Identity",
                "components": ["identity-service"],
                "uptime": "99.91%",
            },
            {
                "name": "Platform Operations",
                "components": ["observability-service", "audit-evidence-service"],
                "uptime": "99.96%",
            },
        ],
    }


def incident_history() -> list[dict]:
    scenarios = load_scenarios()
    base = [
        {
            "id": "hist-1",
            "title": "Playback API OOMKilled SEV1",
            "status": "Resolved",
            "affected": ["playback-service"],
            "duration": "42m",
        },
        {
            "id": "hist-2",
            "title": "Playback CPU throttling SEV2",
            "status": "Monitoring",
            "affected": ["playback-service"],
            "duration": "18m",
        },
        {
            "id": "hist-3",
            "title": "Billing duplicate capture SEV2",
            "status": "Identified",
            "affected": ["billing-service"],
            "duration": "31m",
        },
        {
            "id": "hist-4",
            "title": "Identity lockout SEV1",
            "status": "Investigating",
            "affected": ["identity-service"],
            "duration": "ongoing",
        },
    ]
    return base + [
        {
            "id": scenario["id"],
            "title": scenario["title"],
            "status": "Resolved" if scenario.get("recovered", True) else "Investigating",
            "affected": scenario["affected_services"],
            "duration": "synthetic",
        }
        for scenario in scenarios
    ]


def incident_updates(incident_id: str | None = None) -> list[dict]:
    updates = [
        {
            "incident_id": "hist-1",
            "timestamp": "2026-06-17 13:04 UTC",
            "status": "Investigating",
            "message": "We are investigating elevated playback start latency in US-East. Customers may see buffering or delayed stream starts.",
        },
        {
            "incident_id": "hist-1",
            "timestamp": "2026-06-17 13:12 UTC",
            "status": "Identified",
            "message": "The issue has been traced to playback-api pods being OOMKilled after memory exceeded the configured limit.",
        },
        {
            "incident_id": "hist-1",
            "timestamp": "2026-06-17 13:31 UTC",
            "status": "Monitoring",
            "message": "Mitigation has been applied. Playback start latency is recovering and the team is monitoring for recurrence.",
        },
        {
            "incident_id": "hist-1",
            "timestamp": "2026-06-17 13:46 UTC",
            "status": "Resolved",
            "message": "Playback latency has returned to normal levels. A post-incident review will identify follow-up actions.",
        },
        {
            "incident_id": "hist-2",
            "timestamp": "2026-06-17 14:02 UTC",
            "status": "Monitoring",
            "message": "CPU throttling mitigation is in place for playback-api. We are watching saturation and p99 start latency.",
        },
        {
            "incident_id": "hist-3",
            "timestamp": "2026-06-17 14:12 UTC",
            "status": "Identified",
            "message": "Billing duplicate capture protection is active while reconciliation checks complete.",
        },
        {
            "incident_id": "hist-4",
            "timestamp": "2026-06-17 14:24 UTC",
            "status": "Investigating",
            "message": "Identity engineers are investigating admin lockouts after an MFA provider policy refresh.",
        },
    ]
    if incident_id:
        return [update for update in updates if update["incident_id"] == incident_id]
    return updates
