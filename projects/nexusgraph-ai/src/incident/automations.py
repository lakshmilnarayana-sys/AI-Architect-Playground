import hashlib
import re
from copy import deepcopy
from pathlib import Path

import yaml

from src.incident.kubernetes import normalize_service_name


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
AUTOMATIONS_PATH = DATA / "firehydrant_runbook_automations.yaml"


FALLBACK_AUTOMATIONS = [
    {
        "id": "fh:auto:sev1-streaming",
        "name": "SEV1 streaming incident kickoff",
        "trigger": {"severity": "SEV1", "services": ["playback-service", "Playback Service"]},
        "actions": [
            "create_incident_channel",
            "create_tracking_ticket",
            "assign_roles",
            "post_status_update",
            "notify_stakeholders",
            "capture_timeline",
            "assign_tasks",
            "escalate_by_severity",
            "generate_retro_summary",
        ],
        "role_assignments": {
            "commander": "on-call incident commander",
            "communications": "support liaison",
            "operations": "streaming-platform engineer",
        },
        "simulated_outputs": {
            "ticket_prefix": "INC",
            "status_template": "Investigating playback availability and latency impact.",
        },
    }
]


def _as_list(payload) -> list[dict]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("automations", "runbook_automations", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    raise ValueError("Automation YAML must contain a list of automations")


def load_automations(path: Path = AUTOMATIONS_PATH) -> list[dict]:
    if not path.exists():
        return deepcopy(FALLBACK_AUTOMATIONS)
    with path.open("r", encoding="utf-8") as fh:
        return deepcopy(_as_list(yaml.safe_load(fh)))


def select_automation(
    severity: str,
    services: list[str],
    path: Path = AUTOMATIONS_PATH,
) -> dict:
    severity_key = str(severity or "").upper()
    service_set = {normalize_service_name(service) for service in services}
    service_match = None
    for automation in load_automations(path):
        trigger = automation.get("trigger", {})
        trigger_services = {
            normalize_service_name(service) for service in trigger.get("services", [])
        }
        if service_set & trigger_services and service_match is None:
            service_match = automation
        if str(trigger.get("severity", "")).upper() == severity_key and service_set & trigger_services:
            return automation
    if service_match:
        return service_match
    raise KeyError(f"No automation for {severity} {services}")


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:48] or "incident"


def execute_automation(automation: dict, incident_id: str, title: str) -> dict:
    suffix = hashlib.sha1(incident_id.encode("utf-8")).hexdigest()[:6].upper()
    outputs = automation.get("simulated_outputs", {})
    channel = outputs.get("channel", f"#inc-{_slug(title)}")
    ticket = outputs.get("ticket") or f"{outputs.get('ticket_prefix', 'INC')}-{suffix}"
    timeline = [
        {
            "action": action,
            "status": "simulated",
            "detail": f"{action} completed for {title}",
        }
        for action in automation.get("actions", [])
    ]
    return {
        "automation_id": automation["id"],
        "channel": channel,
        "ticket": ticket,
        "status_update": outputs.get("status_template", title),
        "role_assignments": deepcopy(automation.get("role_assignments", {})),
        "timeline": timeline,
    }
