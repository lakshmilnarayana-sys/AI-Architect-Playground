from __future__ import annotations

import os
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
    traffic_profile = config.get("traffic_profile", {}) or {}
    observability = config.get("observability", {}) or {}
    storage = config.get("storage", {}) or {}
    protocols = config.get("protocols", {}) or {}
    distributed = config.get("distributed", {}) or {}
    profiling = config.get("profiling", {}) or {}
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
        "capacity_probe_rps": test.get("capacity_probe_rps"),
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
        "traffic_profile": {
            "enabled": bool(traffic_profile.get("enabled", False)),
            "source": traffic_profile.get("source", "prometheus"),
            "lookback": traffic_profile.get("lookback", "6h"),
            "peak_multiplier": float(traffic_profile.get("peak_multiplier", 1.5)),
            "endpoint_label": traffic_profile.get("endpoint_label", "route"),
            "request_rate_query": traffic_profile.get(
                "request_rate_query",
                'sum by (route) (rate(http_requests_total{service="{service}"}[5m]))',
            ),
        },
        "observability": _resolve_observability_config(observability, traffic_profile),
        "protocols": protocols,
        "distributed": {
            "enabled": bool(distributed.get("enabled", False)),
            "workers": int(distributed.get("workers", 1)),
            "compose_service": distributed.get("compose_service", "perfagent"),
        },
        "profiling": {
            "auto_capture": bool(profiling.get("auto_capture", False)),
            "duration_seconds": int(profiling.get("duration_seconds", 60)),
            "pid": profiling.get("pid"),
            "profile_endpoint": profiling.get("profile_endpoint"),
            "container": profiling.get("container"),
        },
        "storage": {
            "enabled": bool(storage.get("enabled", True)),
            "backend": storage.get("backend", "sqlite"),
            "path": storage.get("path", "./outputs/perfagent.db"),
            "dsn": storage.get("dsn"),
            "dsn_env": storage.get("dsn_env", "PERFAGENT_DATABASE_URL"),
            "vector_dsn": storage.get("vector_dsn"),
            "vector_dsn_env": storage.get("vector_dsn_env", "PERFAGENT_VECTOR_DSN"),
            "retention_days": int(storage.get("retention_days", 30)),
        },
    }
    for key, value in cli_values.items():
        if value is not None:
            if key in {"cpu_allocation", "memory_allocation", "disk_allocation", "image_tag"}:
                resolved["service_resources"][key] = value
            elif key in {"llm_enabled", "llm_provider", "llm_model", "llm_base_url"}:
                llm_key = key.replace("llm_", "")
                resolved["llm"][llm_key] = value
            elif key in {"profile_auto", "profile_pid", "profile_endpoint", "profile_container"}:
                profile_key = key.replace("profile_", "")
                if profile_key == "auto":
                    profile_key = "auto_capture"
                resolved["profiling"][profile_key] = value
            elif key == "traffic_profile_mode":
                resolved["traffic_profile"]["enabled"] = value == "production"
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


def _resolve_observability_config(observability: dict[str, Any], traffic_profile: dict[str, Any]) -> dict[str, Any]:
    provider = str(traffic_profile.get("source") or observability.get("provider") or "prometheus").lower()
    provider_config = dict(observability.get(provider, {}) or {})
    provider_config.update({key: value for key, value in observability.items() if key not in {"datadog", "newrelic", "new_relic", "elasticsearch", "elk"}})
    provider_config.update({key: value for key, value in traffic_profile.items() if key not in {"enabled", "source"}})
    provider_config["provider"] = provider
    for key in ("api_key", "app_key", "account_id"):
        env_name = provider_config.get(f"{key}_env")
        if env_name and os.getenv(str(env_name)):
            provider_config[key] = os.getenv(str(env_name))
    if provider == "datadog" and provider_config.get("site") and not str(provider_config["site"]).startswith("http"):
        provider_config["site"] = "https://api." + str(provider_config["site"])
    if provider == "elasticsearch" and provider_config.get("url") and not provider_config.get("base_url"):
        provider_config["base_url"] = provider_config["url"]
    return provider_config


def default_strategy(
    duration: str,
    slo_p95_ms: int,
    slo_error_rate_percent: float,
    *,
    mode: str = "standard",
    capacity_probe_rps: int | None = None,
) -> dict[str, Any]:
    if mode == "capacity":
        if capacity_probe_rps:
            return capacity_probe_strategy(duration, slo_p95_ms, slo_error_rate_percent, int(capacity_probe_rps))
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


def capacity_probe_strategy(
    duration: str,
    slo_p95_ms: int,
    slo_error_rate_percent: float,
    target_rps: int,
) -> dict[str, Any]:
    edge_duration = _edge_phase_duration(duration)
    target_rps = max(1, int(target_rps))
    warmup_rps = max(1, int(target_rps * 0.25))
    phases = [
        {"name": "warmup", "duration": edge_duration, "target_rps": warmup_rps},
        {"name": f"capacity_probe_{target_rps}", "duration": duration, "target_rps": target_rps},
        {"name": "recovery", "duration": edge_duration, "target_rps": warmup_rps},
    ]
    return {
        "duration": duration,
        "mode": "capacity",
        "traffic_model": "capacity-probe",
        "capacity_probe_rps": target_rps,
        "phases": phases,
        "stages": [{"duration": phase["duration"], "target": max(1, int(phase["target_rps"] / 10))} for phase in phases],
        "thresholds": {
            "p95_latency_ms": slo_p95_ms,
            "error_rate_percent": slo_error_rate_percent,
        },
    }


def derive_strategy_from_traffic_profile(
    traffic_profile: dict[str, Any],
    *,
    duration: str,
    slo_p95_ms: int,
    slo_error_rate_percent: float,
) -> dict[str, Any]:
    production_rps = float(traffic_profile.get("production_like_rps", 0) or 0)
    peak_rps = float(traffic_profile.get("peak_rps", production_rps) or production_rps)
    warmup_rps = max(1, int(production_rps * 0.25)) if production_rps else 1
    return {
        "duration": duration,
        "mode": "production-traffic",
        "traffic_model": "observed-production",
        "phases": [
            {"name": "warmup", "duration": _edge_phase_duration(duration), "target_rps": warmup_rps},
            {"name": "production_like", "duration": duration, "target_rps": production_rps},
            {"name": "observed_peak", "duration": duration, "target_rps": peak_rps},
            {"name": "recovery", "duration": _edge_phase_duration(duration), "target_rps": warmup_rps},
        ],
        "stages": [
            {"duration": _edge_phase_duration(duration), "target": max(1, int(warmup_rps / 10))},
            {"duration": duration, "target": max(1, int(production_rps / 10))},
            {"duration": duration, "target": max(1, int(peak_rps / 10))},
            {"duration": _edge_phase_duration(duration), "target": max(1, int(warmup_rps / 10))},
        ],
        "endpoint_mix": traffic_profile.get("endpoint_mix", []),
        "thresholds": {
            "p95_latency_ms": slo_p95_ms,
            "error_rate_percent": slo_error_rate_percent,
        },
    }


def _edge_phase_duration(duration: str) -> str:
    if duration.endswith("s"):
        return duration
    return "1m"
