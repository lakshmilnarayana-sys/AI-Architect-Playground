from __future__ import annotations

import hashlib
import os
from copy import deepcopy
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STORE = ROOT / "var" / "simulated_jira_incidents.yaml"
_STORE_PATH = DEFAULT_STORE


def set_store_path(path: str | Path) -> None:
    global _STORE_PATH
    _STORE_PATH = Path(path)


def store_path() -> Path:
    override = os.getenv("SIMULATED_JIRA_STORE")
    return Path(override) if override else _STORE_PATH


def _load(path: Path | None = None) -> list[dict]:
    path = path or store_path()
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as fh:
        payload = yaml.safe_load(fh) or []
    if isinstance(payload, dict):
        return list(payload.get("issues", []))
    return list(payload)


def _write(issues: list[dict], path: Path | None = None) -> None:
    path = path or store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump({"issues": issues}, fh, sort_keys=False)


def _issue_key(incident_id: str) -> str:
    suffix = hashlib.sha1(incident_id.encode("utf-8")).hexdigest()[:6].upper()
    return f"INC-{suffix}"


def issue_from_state(state: dict) -> dict:
    incident = state.get("incident") or {}
    findings = state.get("findings") or {}
    services = incident.get("affected_services") or []
    return {
        "key": _issue_key(incident.get("id", "incident")),
        "incident_id": incident.get("id"),
        "summary": incident.get("title"),
        "severity": incident.get("severity"),
        "services": services,
        "status": "Mitigated" if findings.get("slo_recovered") else "Investigating",
        "failure_mode": incident.get("failure_mode"),
        "commander": (findings.get("incident_commander") or {}).get("name"),
        "channel": (findings.get("slack_channel") or {}).get("channel"),
        "runbook": (findings.get("remediation") or {}).get("runbook", {}).get("id"),
        "status_page_update": findings.get("status_update"),
        "action_items": findings.get("action_items", []),
        "timeline_events": len(state.get("timeline") or []),
        "duration_minutes": max(1, len(state.get("timeline") or []) * 2),
        "time_to_mitigate_minutes": max(1, len([e for e in state.get("timeline", []) if e.get("phase") != "postmortem"]) * 2),
    }


def save_incident(state: dict, path: Path | None = None) -> dict:
    issue = issue_from_state(state)
    issues = _load(path)
    remaining = [item for item in issues if item.get("incident_id") != issue["incident_id"]]
    remaining.append(deepcopy(issue))
    _write(remaining, path)
    return issue


def query_incident_metrics(path: Path | None = None) -> dict:
    issues = _load(path)
    by_severity: dict[str, int] = {}
    by_service: dict[str, int] = {}
    for issue in issues:
        severity = issue.get("severity") or "Unknown"
        by_severity[severity] = by_severity.get(severity, 0) + 1
        for service in issue.get("services") or ["unknown"]:
            by_service[service] = by_service.get(service, 0) + 1
    total = len(issues)
    mttr_values = [int(issue.get("time_to_mitigate_minutes") or 0) for issue in issues]
    mean_mitigate = round(sum(mttr_values) / total, 1) if total else 0
    return {
        "total_incidents": total,
        "by_severity": by_severity,
        "by_service": by_service,
        "mean_time_to_mitigate_minutes": mean_mitigate,
        "open_incidents": len([issue for issue in issues if issue.get("status") != "Mitigated"]),
        "issues": deepcopy(issues),
    }
