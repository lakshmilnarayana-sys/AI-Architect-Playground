from __future__ import annotations

from typing import Any


DEFAULT_THRESHOLDS = {
    "p95_latency_ms": 500,
    "connection_pool_utilization_percent": 90,
    "consumer_lag": 1000,
    "memory_utilization_percent": 90,
    "error_rate_percent": 1,
}


def analyze_dependencies(
    dependencies: list[dict[str, Any]],
    aligned_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    for dependency in dependencies:
        name = dependency.get("name")
        if not name:
            continue
        safe_name = _safe_column_name(name)
        thresholds = dependency.get("thresholds", {}) or {}
        for metric_name in (dependency.get("metrics") or {}):
            column = f"dep_{safe_name}_{_safe_column_name(metric_name)}"
            values = [float(row.get(column, 0) or 0) for row in aligned_rows if row.get(column, "") != ""]
            if not values:
                continue
            peak = max(values)
            threshold = float(thresholds.get(metric_name, DEFAULT_THRESHOLDS.get(metric_name, 0)))
            if threshold and peak > threshold:
                findings.append(
                    {
                        "dependency": name,
                        "type": dependency.get("type", "unknown"),
                        "role": dependency.get("role", "downstream"),
                        "criticality": dependency.get("criticality", "medium"),
                        "metric": metric_name,
                        "value": peak,
                        "threshold": threshold,
                    }
                )
    return {"dependencies": dependencies, "findings": findings}


def _safe_column_name(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")
