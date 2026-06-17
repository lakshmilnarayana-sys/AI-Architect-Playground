from copy import deepcopy
from pathlib import Path

import yaml

from src.incident.kubernetes import normalize_service_name


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
OBSERVABILITY_SOURCES_PATH = DATA / "observability_sources.yaml"


FALLBACK_SOURCES = [
    {
        "kind": "dashboard",
        "name": "Playback Golden Signals",
        "service": "playback-service",
        "failure_modes": ["oom_kill", "pod_restart", "disk_iops", "cpu_throttle"],
        "query": "service=playback-service",
    },
    {
        "kind": "alert",
        "name": "Playback OOMKilled detector",
        "service": "playback-service",
        "failure_modes": ["oom_kill"],
        "query": "kube_pod_container_status_last_terminated_reason{reason='OOMKilled'}",
    },
    {
        "kind": "trace",
        "name": "Playback start trace exemplar",
        "service": "playback-service",
        "failure_modes": ["oom_kill", "pod_restart"],
        "query": "service.name=playback-service operation=StartPlayback",
    },
    {
        "kind": "external_logging",
        "name": "OpenSearch",
        "recommendation": "Ship Kubernetes, app, and ingress logs to OpenSearch using Fluent Bit; index by service, namespace, pod, and incident_id.",
    },
    {
        "kind": "observability",
        "name": "Grafana Cloud",
        "recommendation": "Use Prometheus metrics, Loki logs, Tempo traces, and Grafana dashboards for golden signals and incident overlays.",
    },
]


def _as_list(payload) -> list[dict]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("sources", "observability_sources", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    raise ValueError("Observability sources YAML must contain a list of records")


def load_observability_sources(path: Path = OBSERVABILITY_SOURCES_PATH) -> list[dict]:
    if not path.exists():
        return deepcopy(FALLBACK_SOURCES)
    with path.open("r", encoding="utf-8") as fh:
        return deepcopy(_as_list(yaml.safe_load(fh)))


def _matches_service(item: dict, service: str) -> bool:
    if not item.get("service"):
        return True
    return normalize_service_name(item["service"]) == normalize_service_name(service)


def _matches_failure_mode(item: dict, failure_mode: str) -> bool:
    modes = item.get("failure_modes")
    if not modes:
        return True
    return failure_mode in modes


def get_observability_evidence(
    service: str,
    failure_mode: str,
    path: Path = OBSERVABILITY_SOURCES_PATH,
) -> list[dict]:
    evidence = [
        item
        for item in load_observability_sources(path)
        if item.get("kind") in {"dashboard", "alert", "trace"}
        and _matches_service(item, service)
        and _matches_failure_mode(item, failure_mode)
    ]
    kinds = {item["kind"] for item in evidence}
    defaults = [
        {"kind": "dashboard", "name": "Playback Golden Signals", "query": f"service={service}"},
        {"kind": "alert", "name": f"{failure_mode} detector", "query": f"failure_mode={failure_mode}"},
        {"kind": "trace", "name": "Checkout/playback trace exemplar", "query": f"service.name={service}"},
    ]
    evidence.extend(item for item in defaults if item["kind"] not in kinds)
    seen = set()
    unique = []
    for item in evidence:
        key = (item.get("kind"), item.get("name"), item.get("query"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def external_recommendations(path: Path = OBSERVABILITY_SOURCES_PATH) -> list[dict]:
    recommendations = []
    for item in load_observability_sources(path):
        if item.get("kind") not in {"external_logging", "observability", "external_observability"}:
            continue
        recommendation = str(item.get("recommendation", ""))
        name = item.get("name")
        if not name and "OpenSearch" in recommendation:
            name = "OpenSearch"
        if not name and "Grafana" in recommendation:
            name = "Grafana Cloud"
        recommendations.append({**item, "name": name or item.get("kind", "recommendation")})
    return recommendations
