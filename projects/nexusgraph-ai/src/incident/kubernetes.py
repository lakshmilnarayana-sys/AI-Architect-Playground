from copy import deepcopy
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
KUBERNETES_RESOURCES_PATH = DATA / "kubernetes_resources.yaml"


FALLBACK_RESOURCES = [
    {
        "service": "playback-service",
        "cluster": "streamflix-prod-use1",
        "namespace": "streamflix-prod",
        "workload": {"kind": "Deployment", "name": "playback-api"},
        "kv": {"owner": "streaming-platform"},
        "resources": {
            "limits": {"cpu": "1000m", "memory": "1024Mi"},
            "requests": {"cpu": "500m", "memory": "512Mi"},
        },
        "failure_modes": {
            "oom_kill": {
                "enabled": False,
                "symptom": "OOMKilled",
                "trigger": {
                    "restart_count_delta": 4,
                    "container": "playback-api",
                    "memory_working_set": "1248Mi",
                },
            },
            "pod_restart": {
                "enabled": False,
                "symptom": "CrashLoopBackOff",
                "trigger": {"restart_count_delta": 7, "exit_code": 137},
            },
            "disk_iops": {
                "enabled": False,
                "symptom": "VolumeLatencyHigh",
                "trigger": {"restart_count_delta": 0, "pvc_latency_ms": 180},
            },
            "cpu_throttle": {
                "enabled": False,
                "symptom": "CPUThrottled",
                "trigger": {"restart_count_delta": 0, "throttling_ratio": 0.42},
            },
        },
    }
]


def _as_list(payload) -> list[dict]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("resources", "kubernetes_resources", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    raise ValueError("Kubernetes resources YAML must contain a list of resources")


def load_kubernetes_resources(path: Path = KUBERNETES_RESOURCES_PATH) -> list[dict]:
    if not path.exists():
        return deepcopy(FALLBACK_RESOURCES)
    with path.open("r", encoding="utf-8") as fh:
        return deepcopy(_as_list(yaml.safe_load(fh)))


def normalize_service_name(service: str) -> str:
    return str(service or "").strip().lower().replace("_", "-").replace(" ", "-")


def get_service_resource(service: str, path: Path = KUBERNETES_RESOURCES_PATH) -> dict:
    needle = normalize_service_name(service)
    for resource in load_kubernetes_resources(path):
        aliases = {
            normalize_service_name(resource.get("service", "")),
            normalize_service_name(resource.get("name", "")),
            normalize_service_name(resource.get("id", "")),
        }
        aliases |= {normalize_service_name(alias) for alias in resource.get("aliases", [])}
        if needle in aliases:
            return deepcopy(resource)
    raise KeyError(f"No Kubernetes resource modeled for {service}")


def healthy_runtime(resource: dict) -> dict:
    workload = resource.get("workload") or {}
    return {
        "service": resource["service"],
        "cluster": resource["cluster"],
        "namespace": resource["namespace"],
        "workload": workload.get("name", resource["service"]),
        "active_failure": None,
        "pod_status": "Running",
        "health": "healthy",
        "restart_count_delta": 0,
        "signals": {},
    }


def inject_failure(resource: dict, failure_mode: str) -> dict:
    modes = resource.get("failure_modes", {})
    if failure_mode not in modes:
        raise KeyError(f"{resource['service']} does not model {failure_mode}")
    mode = modes[failure_mode]
    trigger = dict(mode.get("trigger", {}))
    return {
        **healthy_runtime(resource),
        "active_failure": failure_mode,
        "pod_status": mode.get("symptom", "Degraded"),
        "health": "degraded",
        "restart_count_delta": int(trigger.get("restart_count_delta", 0)),
        "signals": trigger,
    }


def clear_failure(resource: dict) -> dict:
    return healthy_runtime(resource)
