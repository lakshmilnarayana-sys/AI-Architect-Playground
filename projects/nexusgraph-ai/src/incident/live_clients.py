"""Thin HTTP clients + env-gated live-mode toggle for the incident agent.

All live behavior is opt-in via INCIDENT_LIVE; every call returns None on any
error so callers fall back to deterministic behavior and never raise.
"""
from __future__ import annotations

import json
import os
import urllib.request

_DEFAULTS = {
    "slack": "http://localhost:18100",
    "jira": "http://localhost:18101",
    "oncall": "http://localhost:18102",
    "prometheus": "http://localhost:9090",
    "alertmanager": "http://localhost:9093",
}
_ENV = {
    "slack": "SLACK_MOCK_URL",
    "jira": "JIRA_MOCK_URL",
    "oncall": "ONCALL_REGISTRY_URL",
    "prometheus": "PROMETHEUS_URL",
    "alertmanager": "ALERTMANAGER_URL",
}


def live_enabled() -> bool:
    return str(os.getenv("INCIDENT_LIVE", "")).strip().lower() in ("1", "true", "yes", "on")


def endpoint(name: str) -> str:
    return os.getenv(_ENV[name], _DEFAULTS[name]).rstrip("/")


def http_post_json(url: str, payload: dict, timeout: float = 3.0):
    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers={"content-type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
        return json.loads(body) if body else {}
    except Exception:
        return None


def http_get_json(url: str, timeout: float = 3.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode()
        return json.loads(body) if body else None
    except Exception:
        return None
