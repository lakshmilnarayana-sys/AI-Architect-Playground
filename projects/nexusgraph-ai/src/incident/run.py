"""Manual + programmatic entrypoint to run the incident pipeline for one service."""
from __future__ import annotations

import argparse

from src.incident.state import new_incident, IncidentState
from src.incident.graph_lookup import GraphContext
from src.incident.supervisor import run_incident


def seed_from_alert(alert: dict) -> IncidentState:
    labels = alert.get("labels", {}) or {}
    service = labels.get("service") or labels.get("pod") or "unknown-service"
    severity = labels.get("severity", "SEV3")
    failure_mode = labels.get("failure_mode")
    alertname = labels.get("alertname", "StreamFlixAlert")
    state = new_incident(
        incident_id=f"incident:{alertname}:{service}",
        title=f"{alertname} on {service}",
        severity=severity,
        affected_services=[service],
        signal=(alert.get("annotations", {}) or {}).get("summary", alertname),
    )
    if failure_mode:
        state["incident"]["failure_mode"] = failure_mode
    state["incident"]["scenario_id"] = alertname
    return state


def run_for_service(service: str, failure_mode: str | None = None, severity: str = "SEV2") -> dict:
    state = new_incident(
        incident_id=f"incident:manual:{service}",
        title=f"Manual incident on {service}",
        severity=severity,
        affected_services=[service],
        signal=f"manual run for {service}",
    )
    if failure_mode:
        state["incident"]["failure_mode"] = failure_mode
    ctx = GraphContext(use_neo4j=False)
    return run_incident(state, ctx=ctx, use_vector=False)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--service", required=True)
    ap.add_argument("--failure-mode", default=None)
    ap.add_argument("--severity", default="SEV2")
    a = ap.parse_args()
    final = run_for_service(a.service, a.failure_mode, a.severity)
    print(f"incident complete: {len(final.get('timeline', []))} timeline events, "
          f"phase={final.get('phase')}")
    jira = (final.get("findings") or {}).get("jira_issue")
    if jira:
        print(f"jira: {jira.get('key')}")


if __name__ == "__main__":
    main()
