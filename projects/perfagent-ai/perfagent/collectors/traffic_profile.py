from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib import parse, request


def collect_prometheus_traffic_profile(
    prometheus_url: str | None,
    service_label: str | None,
    config: dict[str, Any],
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    step_seconds: int = 300,
) -> dict[str, Any]:
    if not prometheus_url or not config.get("enabled", True):
        return {"enabled": False, "source": "none", "endpoint_mix": []}
    end = end or datetime.now(UTC)
    start = start or end - _lookback_delta(str(config.get("lookback", "6h")))
    endpoint_label = config.get("endpoint_label", "route")
    query_template = config.get(
        "request_rate_query",
        'sum by (route) (rate(http_requests_total{service="{service}"}[5m]))',
    )
    query = query_template.replace("{service}", _escape_label_value(service_label or ""))
    rows = _query_range_with_labels(prometheus_url, query, start, end, step_seconds)
    totals: dict[str, float] = {}
    for row in rows:
        path = row.get("labels", {}).get(endpoint_label) or row.get("labels", {}).get("path")
        if not path:
            continue
        totals[path] = max(totals.get(path, 0.0), float(row.get("value", 0) or 0))
    total_rps = sum(totals.values())
    endpoint_mix = [
        {"path": path, "observed_rps": round(rps, 6), "weight": round((rps / total_rps) if total_rps else 0, 6)}
        for path, rps in sorted(totals.items(), key=lambda item: item[1], reverse=True)
    ]
    peak_multiplier = float(config.get("peak_multiplier", 1.5))
    return {
        "enabled": True,
        "source": "prometheus",
        "lookback": config.get("lookback", "6h"),
        "endpoint_label": endpoint_label,
        "observed_peak_rps": round(total_rps, 6),
        "production_like_rps": round(total_rps, 6),
        "peak_rps": round(total_rps * peak_multiplier, 6),
        "peak_multiplier": peak_multiplier,
        "endpoint_mix": endpoint_mix,
        "query": query,
    }


def _query_range_with_labels(
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
        labels = series.get("metric", {})
        for timestamp, value in series.get("values", []):
            rows.append({"timestamp": _format_unix_time(float(timestamp)), "value": _safe_float(value), "labels": labels})
    return rows


def _lookback_delta(value: str) -> timedelta:
    value = value.strip()
    if value.endswith("m"):
        return timedelta(minutes=float(value[:-1]))
    if value.endswith("h"):
        return timedelta(hours=float(value[:-1]))
    if value.endswith("d"):
        return timedelta(days=float(value[:-1]))
    return timedelta(seconds=float(value.rstrip("s")))


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
