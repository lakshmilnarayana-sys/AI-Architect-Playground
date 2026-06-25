"""Manual + programmatic entrypoint to run the incident pipeline for one service."""
from __future__ import annotations

import argparse
import re

from src.incident.state import new_incident, IncidentState
from src.incident.graph_lookup import GraphContext
from src.incident.supervisor import run_incident


def _service_from_labels(labels: dict) -> str:
    svc = labels.get("service")
    if svc:
        return svc
    pod = labels.get("pod", "")
    if pod:
        # strip trailing "-<rshash>-<podhash>" (deployment name remains)
        return re.sub(r"-[a-z0-9]+-[a-z0-9]+$", "", pod)
    return "unknown-service"


def seed_from_alert(alert: dict) -> IncidentState:
    labels = alert.get("labels", {}) or {}
    service = _service_from_labels(labels)
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
        state["incident"]["simulate_failure"] = True
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
        state["incident"]["simulate_failure"] = True
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
