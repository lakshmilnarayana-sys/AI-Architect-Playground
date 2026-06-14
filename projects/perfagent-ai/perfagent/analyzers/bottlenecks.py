from __future__ import annotations

from typing import Any


def classify_bottleneck(features: dict[str, Any]) -> dict[str, Any]:
    latency_rises = features.get("max_p95_latency_ms", 0) > features.get("slo_p95_latency_ms", 0)
    error_breach = features.get("max_error_rate_percent", 0) > features.get("slo_error_rate_percent", 0)
    evidence: list[str] = []
    dependency_result = _dependency_bottleneck(features.get("dependency_findings", []), latency_rises)
    if dependency_result:
        return dependency_result

    if latency_rises and features.get("cpu_peak_percent", 0) > 85:
        evidence.extend(["p95 latency breached the configured SLO", "CPU usage exceeded 85%"])
        return _result("cpu_saturation", "high", evidence)

    if latency_rises and features.get("cpu_throttling_peak_percent", 0) > 5:
        evidence.extend(["p95 latency breached the configured SLO", "CPU throttling exceeded 5%"])
        return _result("cpu_limit_or_throttling", "high", evidence)

    if (
        features.get("memory_growth_rate_mb_per_min", 0) > 0
        and not features.get("memory_recovered", True)
    ):
        evidence.extend(["Memory grew during load", "Memory did not recover after load dropped"])
        return _result("memory_leak_or_unbounded_cache", "medium", evidence)

    if latency_rises and error_breach:
        evidence.extend(["p95 latency breached the configured SLO", "Error rate exceeded the configured SLO"])
        return _result("overloaded_service_or_dependency", "medium", evidence)

    if latency_rises:
        evidence.extend(["p95 latency breached the configured SLO", "CPU and memory did not show saturation"])
        return _result("dependency_or_unknown", "medium", evidence)

    evidence.append("Observed metrics stayed within configured SLO thresholds")
    return _result("none_detected", "medium", evidence)


def _result(bottleneck: str, confidence: str, evidence: list[str]) -> dict[str, Any]:
    return {
        "bottleneck": bottleneck,
        "confidence": confidence,
        "evidence": evidence,
        "recommendations": _recommendations(bottleneck),
        "missing_metrics": ["dependency latency", "database query latency", "connection pool saturation"]
        if bottleneck == "dependency_or_unknown"
        else [],
    }


def _recommendations(bottleneck: str) -> list[str]:
    recommendations = {
        "cpu_saturation": [
            "Profile CPU hot paths under representative load.",
            "Review runtime concurrency settings and CPU limits.",
            "Re-run the stress test after optimization or capacity changes.",
        ],
        "cpu_limit_or_throttling": [
            "Inspect container CPU limits and throttling metrics.",
            "Increase CPU limits or reduce per-request CPU cost.",
        ],
        "memory_leak_or_unbounded_cache": [
            "Capture heap profiles during ramp and recovery phases.",
            "Audit caches and request-scoped allocations.",
        ],
        "overloaded_service_or_dependency": [
            "Add dependency-level latency and error metrics.",
            "Inspect database, queue, and external API saturation.",
        ],
        "dependency_or_unknown": [
            "Add dependency-level metrics for database, Redis, queue, and external APIs.",
            "Inspect slow queries and connection pool usage.",
            "Re-run stress testing with dependency metrics enabled.",
        ],
    }
    return recommendations.get(bottleneck, ["Keep the generated performance suite in release validation."])


def _dependency_bottleneck(findings: list[dict[str, Any]], latency_rises: bool) -> dict[str, Any] | None:
    if not latency_rises or not findings:
        return None
    for finding in findings:
        dependency = finding.get("dependency", "dependency")
        dependency_type = finding.get("type", "dependency")
        metric = finding.get("metric", "")
        value = finding.get("value")
        threshold = finding.get("threshold")
        evidence = [
            "p95 latency breached the configured SLO",
            f"{dependency} {metric} reached {value} against threshold {threshold}",
        ]
        if "connection_pool" in metric and dependency_type in {"postgres", "mysql", "cassandra", "database"}:
            return _result("database_connection_pool_saturation", "high", evidence)
        if "lag" in metric and dependency_type == "kafka":
            return _result("kafka_lag_or_broker_saturation", "high", evidence)
        if "eviction" in metric or dependency_type == "redis" and "memory" in metric:
            return _result("redis_memory_or_latency", "medium", evidence)
        if dependency_type in {"elasticsearch", "opensearch"}:
            return _result("search_cluster_saturation", "medium", evidence)
        if "latency" in metric:
            return _result("dependency_latency", "medium", evidence)
    return None
