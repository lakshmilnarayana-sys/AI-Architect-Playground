from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_run_config(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    return yaml.safe_load(path.read_text()) or {}


def resolve_evaluate_options(config: dict[str, Any], cli_values: dict[str, Any]) -> dict[str, Any]:
    prometheus = config.get("prometheus", {}) or {}
    output = config.get("output", {}) or {}
    service = config.get("service", {}) or {}
    slo = config.get("slo", {}) or {}
    test = config.get("test", {}) or {}
    llm = config.get("llm", {}) or {}
    dependencies = _normalize_dependencies(config.get("dependencies", []))
    prometheus_enabled = prometheus.get("enabled", bool(prometheus.get("url")))
    resolved = {
        "service_name": config.get("service_name"),
        "openapi_path": config.get("openapi_path"),
        "target_url": config.get("target_url"),
        "runtime": config.get("runtime"),
        "slo_p95_ms": slo.get("p95_latency_ms"),
        "slo_error_rate_percent": slo.get("error_rate_percent"),
        "duration": test.get("duration", "10m"),
        "engine": test.get("engine", "k6"),
        "mode": test.get("mode", "standard"),
        "output_dir": output.get("directory"),
        "prometheus_url": prometheus.get("url") if prometheus_enabled else None,
        "prometheus_service_label": prometheus.get("service_label"),
        "prometheus_query_config_path": prometheus.get("query_config"),
        "service_resources": {
            "cpu_allocation": service.get("cpu_allocation"),
            "memory_allocation": service.get("memory_allocation"),
            "disk_allocation": service.get("disk_allocation"),
            "image_tag": service.get("image_tag"),
        },
        "dependencies": dependencies,
        "llm": {
            "enabled": bool(llm.get("enabled", False)),
            "provider": llm.get("provider", "ollama"),
            "model": llm.get("model", "llama3.2"),
            "base_url": llm.get("base_url", "http://localhost:11434"),
        },
    }
    for key, value in cli_values.items():
        if value is not None:
            if key in {"cpu_allocation", "memory_allocation", "disk_allocation", "image_tag"}:
                resolved["service_resources"][key] = value
            elif key in {"llm_enabled", "llm_provider", "llm_model", "llm_base_url"}:
                llm_key = key.replace("llm_", "")
                resolved["llm"][llm_key] = value
            else:
                resolved[key] = value
    return resolved


def _normalize_dependencies(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        dependencies = []
        for name, item in value.items():
            if isinstance(item, dict):
                dependency = dict(item)
                dependency.setdefault("name", name)
                dependency.setdefault("metrics", {})
                dependencies.append(dependency)
        return dependencies
    if isinstance(value, list):
        dependencies = []
        for item in value:
            if isinstance(item, dict):
                dependency = dict(item)
                dependency.setdefault("metrics", {})
                dependencies.append(dependency)
        return dependencies
    return []


def default_strategy(
    duration: str,
    slo_p95_ms: int,
    slo_error_rate_percent: float,
    *,
    mode: str = "standard",
) -> dict[str, Any]:
    if mode == "capacity":
        return capacity_strategy(duration, slo_p95_ms, slo_error_rate_percent)
    edge_duration = _edge_phase_duration(duration)
    return {
        "duration": duration,
        "mode": mode,
        "traffic_model": "ramping-vus",
        "phases": [
            {"name": "warmup", "duration": edge_duration, "target_rps": 50},
            {"name": "baseline", "duration": duration, "target_rps": 200},
            {"name": "stress", "duration": duration, "target_rps": 500},
            {"name": "recovery", "duration": edge_duration, "target_rps": 50},
        ],
        "stages": [
            {"duration": edge_duration, "target": 10},
            {"duration": duration, "target": 50},
            {"duration": duration, "target": 100},
            {"duration": edge_duration, "target": 10},
        ],
        "thresholds": {
            "p95_latency_ms": slo_p95_ms,
            "error_rate_percent": slo_error_rate_percent,
        },
    }


def capacity_strategy(duration: str, slo_p95_ms: int, slo_error_rate_percent: float) -> dict[str, Any]:
    edge_duration = _edge_phase_duration(duration)
    phases = [
        {"name": "warmup", "duration": edge_duration, "target_rps": 25},
        {"name": "capacity_probe_50", "duration": duration, "target_rps": 50},
        {"name": "capacity_probe_100", "duration": duration, "target_rps": 100},
        {"name": "capacity_probe_200", "duration": duration, "target_rps": 200},
        {"name": "capacity_probe_400", "duration": duration, "target_rps": 400},
        {"name": "capacity_probe_800", "duration": duration, "target_rps": 800},
        {"name": "recovery", "duration": edge_duration, "target_rps": 25},
    ]
    return {
        "duration": duration,
        "mode": "capacity",
        "traffic_model": "capacity-ramp",
        "phases": phases,
        "stages": [
            {"duration": phase["duration"], "target": max(1, int(phase["target_rps"] / 10))}
            for phase in phases
        ],
        "thresholds": {
            "p95_latency_ms": slo_p95_ms,
            "error_rate_percent": slo_error_rate_percent,
        },
    }


def _edge_phase_duration(duration: str) -> str:
    if duration.endswith("s"):
        return duration
    return "1m"
