from copy import deepcopy
from pathlib import Path

import yaml

from src.incident.kubernetes import normalize_service_name


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
SERVICE_LOGS_PATH = DATA / "service_logs.yaml"


FALLBACK_LOGS = [
    {
        "timestamp": "2026-06-17T10:00:00Z",
        "scenario_id": "playback-oom-sev1",
        "service": "playback-service",
        "severity": "ERROR",
        "message": "Pod playback-api-7d9f was OOMKilled after memory exceeded 1024Mi limit.",
    },
    {
        "timestamp": "2026-06-17T10:01:00Z",
        "scenario_id": "playback-oom-sev1",
        "service": "playback-service",
        "severity": "WARN",
        "message": "Restart count increased for playback-api deployment.",
    },
]


def _as_list(payload) -> list[dict]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("logs", "service_logs", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    raise ValueError("Service logs YAML must contain a list of log records")


def load_service_logs(path: Path = SERVICE_LOGS_PATH) -> list[dict]:
    if not path.exists():
        return deepcopy(FALLBACK_LOGS)
    with path.open("r", encoding="utf-8") as fh:
        return deepcopy(_as_list(yaml.safe_load(fh)))


def _timestamp(log: dict) -> str:
    return str(log.get("timestamp") or log.get("ts") or "")


def _severity(log: dict) -> str:
    return str(log.get("severity") or log.get("level") or "")


def get_logs_for_incident(
    scenario_id: str,
    service: str | None = None,
    severity: str | None = None,
    start: str | None = None,
    end: str | None = None,
    path: Path = SERVICE_LOGS_PATH,
) -> list[dict]:
    service_key = normalize_service_name(service) if service else None
    severity_key = severity.upper() if severity else None
    results = []
    scenario_logs = []
    for log in load_service_logs(path):
        if log.get("scenario_id") != scenario_id:
            continue
        scenario_logs.append(log)
        if service_key and normalize_service_name(log.get("service", "")) != service_key:
            continue
        if severity_key and _severity(log).upper() != severity_key:
            continue
        ts = _timestamp(log)
        if start and ts and ts < start:
            continue
        if end and ts and ts > end:
            continue
        normalized = dict(log)
        normalized.setdefault("timestamp", _timestamp(log))
        normalized.setdefault("severity", _severity(log).upper())
        results.append(normalized)
    if not results and service_key and scenario_logs:
        for log in scenario_logs:
            normalized = dict(log)
            normalized.setdefault("timestamp", _timestamp(log))
            normalized.setdefault("severity", _severity(log).upper())
            normalized["fallback_match"] = True
            normalized["requested_service"] = service
            results.append(normalized)
    return sorted(results, key=_timestamp)
