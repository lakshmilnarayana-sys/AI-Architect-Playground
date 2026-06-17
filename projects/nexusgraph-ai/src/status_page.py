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
