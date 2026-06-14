from __future__ import annotations

from typing import Any


def extract_features(
    k6_summary: dict[str, Any],
    aligned_timeseries: list[dict[str, Any]],
    *,
    slo_p95_ms: int,
    slo_error_rate_percent: float,
) -> dict[str, Any]:
    metrics = k6_summary.get("metrics", {})
    duration = metrics.get("http_req_duration", {})
    failed = metrics.get("http_req_failed", {})
    http_reqs = metrics.get("http_reqs", {})

    p95 = _percentile(duration, "p(95)")
    p99 = _percentile(duration, "p(99)")
    error_rate_percent = round(_error_rate(failed) * 100, 4)
    peak_rps = max([float(row.get("rps", 0)) for row in aligned_timeseries] or [float(http_reqs.get("rate", 0))])
    ordered_timeseries = _ordered_rows(aligned_timeseries)
    first_breach = _first_slo_breach(ordered_timeseries, slo_p95_ms, slo_error_rate_percent)

    features = {
        "peak_rps": peak_rps,
        "stable_rps": float(http_reqs.get("rate", 0)),
        "request_count": int(http_reqs.get("count", 0)),
        "max_p95_latency_ms": p95,
        "max_p99_latency_ms": p99,
        "average_p95_latency_ms": p95,
        "max_error_rate_percent": error_rate_percent,
        "first_slo_breach_timestamp": first_breach.get("timestamp"),
        "first_slo_breach_phase": first_breach.get("phase"),
        "breaking_point_rps": first_breach.get("rps"),
        "cpu_peak_percent": max([float(row.get("cpu_percent", 0) or 0) for row in aligned_timeseries] or [0]),
        "memory_peak_mb": max([float(row.get("memory_mb", 0) or 0) for row in aligned_timeseries] or [0]),
        "memory_growth_rate_mb_per_min": 0,
        "memory_recovered": True,
        "cpu_per_1000_rps": 0,
        "recovery_time_seconds": 0,
        "slo_p95_latency_ms": slo_p95_ms,
        "slo_error_rate_percent": slo_error_rate_percent,
    }
    features.update(_capacity_features(ordered_timeseries, features, slo_p95_ms, slo_error_rate_percent))
    features["release_decision"] = release_decision(features, aligned_timeseries)
    return features


def release_decision(features: dict[str, Any], aligned_timeseries: list[dict[str, Any]]) -> str:
    if not aligned_timeseries and features.get("request_count", 0) == 0:
        return "UNKNOWN"

    baseline_breach = any(
        row.get("phase") == "baseline"
        and (
            float(row.get("p95_latency_ms", 0)) > features["slo_p95_latency_ms"]
            or float(row.get("error_rate_percent", 0)) > features["slo_error_rate_percent"]
        )
        for row in aligned_timeseries
    )
    if baseline_breach:
        return "BLOCK"
    if (
        features["max_p95_latency_ms"] > features["slo_p95_latency_ms"]
        or features["max_error_rate_percent"] > features["slo_error_rate_percent"]
    ):
        return "WARN"
    return "PASS"


def _percentile(metric: dict[str, Any], name: str) -> float:
    if "percentiles" in metric:
        return float(metric["percentiles"].get(name, 0))
    return float(metric.get(name, metric.get(name.replace("(", "").replace(")", ""), 0)))


def _error_rate(metric: dict[str, Any]) -> float:
    if "rate" in metric:
        return float(metric["rate"])
    if "value" in metric:
        return float(metric["value"])
    fails = float(metric.get("fails", 0))
    passes = float(metric.get("passes", 0))
    total = fails + passes
    return fails / total if total else 0


def _first_slo_breach(
    rows: list[dict[str, Any]], slo_p95_ms: int, slo_error_rate_percent: float
) -> dict[str, Any]:
    for row in rows:
        if _slo_breach_reason(row, slo_p95_ms, slo_error_rate_percent):
            return row
    return {}


def _ordered_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    if all(row.get("timestamp") for row in rows):
        return sorted(rows, key=lambda row: str(row.get("timestamp")))
    return rows


def _slo_breach_reason(row: dict[str, Any], slo_p95_ms: int, slo_error_rate_percent: float) -> str | None:
    latency_breached = float(row.get("p95_latency_ms", 0)) > slo_p95_ms
    errors_breached = float(row.get("error_rate_percent", 0)) > slo_error_rate_percent
    if latency_breached and errors_breached:
        return "latency_and_error_slo_breach"
    if latency_breached:
        return "latency_slo_breach"
    if errors_breached:
        return "error_slo_breach"
    return None


def _capacity_features(
    rows: list[dict[str, Any]],
    features: dict[str, Any],
    slo_p95_ms: int,
    slo_error_rate_percent: float,
) -> dict[str, Any]:
    sorted_rows = rows
    if not sorted_rows:
        return {
            "estimated_capacity_rps": float(features.get("peak_rps", 0)),
            "capacity_confidence": "low",
            "capacity_basis": "insufficient aligned time-series rows for capacity estimate",
            "headroom_rps": None,
            "capacity_limit_phase": None,
            "capacity_limit_reason": "insufficient_timeseries_rows",
            "capacity_safe_phase": None,
            "capacity_stress_phase": None,
        }

    first_breach_index: int | None = None
    capacity_limit_reason: str | None = None
    for index, row in enumerate(sorted_rows):
        breach_reason = _slo_breach_reason(row, slo_p95_ms, slo_error_rate_percent)
        if breach_reason:
            first_breach_index = index
            capacity_limit_reason = breach_reason
            break

    if first_breach_index is None:
        capacity_row = max(sorted_rows, key=lambda row: float(row.get("rps", 0)))
        estimated_capacity = float(capacity_row.get("rps", 0))
        return {
            "estimated_capacity_rps": estimated_capacity,
            "capacity_confidence": "medium",
            "capacity_basis": "highest observed RPS stayed within SLO",
            "headroom_rps": None,
            "capacity_limit_phase": None,
            "capacity_limit_reason": "slo_not_breached_within_tested_range",
            "capacity_safe_phase": capacity_row.get("phase"),
            "capacity_stress_phase": None,
        }

    safe_rows = sorted_rows[:first_breach_index]
    safe_capacity_row = max(safe_rows, key=lambda row: float(row.get("rps", 0))) if safe_rows else None
    estimated_capacity = float(safe_capacity_row.get("rps", 0)) if safe_capacity_row else 0
    breaking_point = float(sorted_rows[first_breach_index].get("rps", 0))
    return {
        "estimated_capacity_rps": estimated_capacity,
        "capacity_confidence": "medium" if safe_rows else "low",
        "capacity_basis": "highest observed RPS before first SLO breach",
        "headroom_rps": breaking_point - estimated_capacity if breaking_point else None,
        "capacity_limit_phase": sorted_rows[first_breach_index].get("phase"),
        "capacity_limit_reason": capacity_limit_reason,
        "capacity_safe_phase": safe_capacity_row.get("phase") if safe_capacity_row else None,
        "capacity_stress_phase": sorted_rows[first_breach_index].get("phase"),
    }
