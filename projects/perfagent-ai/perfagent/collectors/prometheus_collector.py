from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib import parse, request

import yaml


DEFAULT_QUERIES = {
    "cpu_percent": 'sum(rate(container_cpu_usage_seconds_total{pod=~".*{service}.*"}[1m])) * 100',
    "memory_mb": 'sum(container_memory_working_set_bytes{pod=~".*{service}.*"}) / 1024 / 1024',
    "cpu_throttling_percent": 'sum(rate(container_cpu_cfs_throttled_periods_total{pod=~".*{service}.*"}[1m])) / sum(rate(container_cpu_cfs_periods_total{pod=~".*{service}.*"}[1m])) * 100',
    "pod_restarts": 'sum(kube_pod_container_status_restarts_total{pod=~".*{service}.*"})',
    "service_request_rate": 'sum(rate(http_requests_total{service=~".*{service}.*"}[1m]))',
    "service_error_rate_percent": 'sum(rate(http_requests_total{service=~".*{service}.*",status=~"5.."}[1m])) / sum(rate(http_requests_total{service=~".*{service}.*"}[1m])) * 100',
}


def collect_prometheus_metrics(
    prometheus_url: str | None,
    service_label: str | None,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    step_seconds: int = 10,
    timeout_seconds: int = 10,
    query_templates: dict[str, str] | None = None,
) -> dict[str, Any]:
    if not prometheus_url:
        return {}

    end = end or datetime.now(UTC)
    start = start or end - timedelta(minutes=15)
    service = service_label or ""
    queries = query_templates or DEFAULT_QUERIES
    metrics: dict[str, list[dict[str, Any]]] = {}
    warnings: list[str] = []

    for metric_name, template in queries.items():
        query = template.replace("{service}", _escape_label_value(service))
        try:
            metrics[metric_name] = _query_range(
                prometheus_url,
                query,
                start,
                end,
                step_seconds,
            )
        except Exception as exc:  # pragma: no cover - exact urllib exceptions vary
            metrics[metric_name] = []
            warnings.append(f"Prometheus query failed for {metric_name}: {exc}")

    return {
        "enabled": True,
        "url": prometheus_url.rstrip("/"),
        "service_label": service_label,
        "start": _format_time(start),
        "end": _format_time(end),
        "step_seconds": step_seconds,
        "query_names": list(queries.keys()),
        "metrics": metrics,
        "warnings": warnings,
    }


def load_prometheus_query_config(path: Path | None) -> dict[str, str] | None:
    if path is None:
        return None
    data = yaml.safe_load(path.read_text()) or {}
    queries = data.get("queries", data)
    if not isinstance(queries, dict):
        raise ValueError("Prometheus query config must contain a mapping or a top-level 'queries' mapping")
    normalized: dict[str, str] = {}
    for name, query in queries.items():
        if not isinstance(name, str) or not isinstance(query, str):
            raise ValueError("Prometheus query config keys and values must be strings")
        normalized[name] = query
    return normalized


def validate_prometheus_queries(
    prometheus_url: str,
    service_label: str | None,
    *,
    query_templates: dict[str, str] | None = None,
    step_seconds: int = 10,
) -> dict[str, Any]:
    end = datetime.now(UTC)
    start = end - timedelta(minutes=1)
    queries = query_templates or DEFAULT_QUERIES
    results: dict[str, dict[str, Any]] = {}
    for metric_name, template in queries.items():
        query = template.replace("{service}", _escape_label_value(service_label or ""))
        try:
            rows = _query_range(prometheus_url, query, start, end, step_seconds)
            results[metric_name] = {"available": bool(rows), "sample_count": len(rows), "error": None}
        except Exception as exc:  # pragma: no cover - urllib exceptions vary
            results[metric_name] = {"available": False, "sample_count": 0, "error": str(exc)}
    return {
        "status": "passed" if all(item["available"] for item in results.values()) else "failed",
        "url": prometheus_url.rstrip("/"),
        "service_label": service_label,
        "results": results,
    }


def collect_dependency_metrics(
    prometheus_url: str | None,
    service_label: str | None,
    dependencies: list[dict[str, Any]],
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    step_seconds: int = 10,
) -> dict[str, Any]:
    if not prometheus_url or not dependencies:
        return {"dependencies": {}, "warnings": []}
    end = end or datetime.now(UTC)
    start = start or end - timedelta(minutes=15)
    warnings: list[str] = []
    collected: dict[str, Any] = {}
    for dependency in dependencies:
        name = dependency.get("name")
        if not name:
            continue
        metrics: dict[str, list[dict[str, Any]]] = {}
        for metric_name, template in (dependency.get("metrics") or {}).items():
            query = template.replace("{service}", _escape_label_value(service_label or "")).replace(
                "{dependency}", _escape_label_value(name)
            )
            try:
                metrics[metric_name] = _query_range(prometheus_url, query, start, end, step_seconds)
            except Exception as exc:  # pragma: no cover - urllib exceptions vary
                metrics[metric_name] = []
                warnings.append(f"Prometheus dependency query failed for {name}.{metric_name}: {exc}")
        collected[name] = {
            "type": dependency.get("type", "unknown"),
            "role": dependency.get("role", "downstream"),
            "criticality": dependency.get("criticality", "medium"),
            "metrics": metrics,
        }
    return {"dependencies": collected, "warnings": warnings}


def merge_dependency_metrics(
    aligned_rows: list[dict[str, Any]], dependency_metrics: dict[str, Any]
) -> list[dict[str, Any]]:
    if not dependency_metrics:
        return aligned_rows
    merged = [dict(row) for row in aligned_rows]
    for row in merged:
        timestamp = row.get("timestamp")
        for dependency_name, dependency in dependency_metrics.get("dependencies", {}).items():
            safe_name = _safe_column_name(dependency_name)
            for metric_name, values in dependency.get("metrics", {}).items():
                value = _value_at(values, timestamp)
                if value is not None:
                    row[f"dep_{safe_name}_{_safe_column_name(metric_name)}"] = value
    return merged


def merge_prometheus_metrics(
    aligned_rows: list[dict[str, Any]], prometheus_metrics: dict[str, Any]
) -> list[dict[str, Any]]:
    if not prometheus_metrics:
        return aligned_rows
    metric_values = prometheus_metrics.get("metrics", {})
    merged = [dict(row) for row in aligned_rows]
    for row in merged:
        timestamp = row.get("timestamp")
        for source_name, target_name in [
            ("cpu_percent", "cpu_percent"),
            ("memory_mb", "memory_mb"),
            ("cpu_throttling_percent", "cpu_throttling_percent"),
            ("pod_restarts", "pod_restarts"),
            ("service_request_rate", "service_request_rate"),
            ("service_error_rate_percent", "service_error_rate_percent"),
        ]:
            value = _value_at(metric_values.get(source_name, []), timestamp)
            if value is not None:
                row[target_name] = value
    return merged


def _query_range(
    prometheus_url: str,
    query: str,
    start: datetime,
    end: datetime,
    step_seconds: int,
    *,
    timeout_seconds: int = 10,
) -> list[dict[str, Any]]:
    base = prometheus_url.rstrip("/") + "/api/v1/query_range"
    params = parse.urlencode(
        {
            "query": query,
            "start": _format_time(start),
            "end": _format_time(end),
            "step": str(step_seconds),
        }
    )
    req = request.Request(base + "?" + params, headers={"Accept": "application/json"})
    with request.urlopen(req, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("status") != "success":
        raise RuntimeError(f"Prometheus returned status {payload.get('status')}")
    rows: list[dict[str, Any]] = []
    for series in payload.get("data", {}).get("result", []):
        for timestamp, value in series.get("values", []):
            rows.append({"timestamp": _format_unix_time(float(timestamp)), "value": _safe_float(value)})
    return rows


def _value_at(values: list[dict[str, Any]], timestamp: str | None) -> float | None:
    if not timestamp:
        return None
    for item in values:
        if item.get("timestamp") == timestamp:
            return item.get("value")
    return None


def _format_time(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _format_unix_time(value: float) -> str:
    return datetime.fromtimestamp(value, tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _escape_label_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _safe_column_name(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")
