from __future__ import annotations

import csv
import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


FIELDNAMES = [
    "timestamp",
    "phase",
    "rps",
    "p95_latency_ms",
    "p99_latency_ms",
    "error_rate_percent",
    "virtual_users",
    "cpu_percent",
    "memory_mb",
    "cpu_throttling_percent",
    "pod_restarts",
    "service_request_rate",
    "service_error_rate_percent",
]


def fallback_aligned_timeseries(k6_summary: dict[str, Any]) -> list[dict[str, Any]]:
    metrics = k6_summary.get("metrics", {})
    if not metrics:
        return []
    duration = metrics.get("http_req_duration", {})
    failed = metrics.get("http_req_failed", {})
    return [
        {
            "timestamp": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "phase": "summary",
            "rps": metrics.get("http_reqs", {}).get("rate", 0),
            "p95_latency_ms": _percentile(duration, "p(95)"),
            "p99_latency_ms": _percentile(duration, "p(99)"),
            "error_rate_percent": round(_error_rate(failed) * 100, 4),
            "virtual_users": metrics.get("vus", {}).get("value", metrics.get("vus", {}).get("max", 0)),
            "cpu_percent": 0,
            "memory_mb": 0,
            "cpu_throttling_percent": 0,
        }
    ]


def write_aligned_csv(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    dynamic_fields = sorted({key for row in rows for key in row if key.startswith("dep_")})
    fieldnames = FIELDNAMES + [field for field in dynamic_fields if field not in FIELDNAMES]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    return path


def align_k6_jsonl(path: Path, strategy: dict[str, Any], bucket_seconds: int = 10) -> list[dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []

    points = _read_points(path)
    if not points:
        return []

    start_time = min(point["time"] for point in points)
    aligned_start = _floor_time(start_time, bucket_seconds)
    windows = phase_windows(strategy)
    buckets: dict[int, dict[str, Any]] = {}

    for point in points:
        offset = int((point["time"] - aligned_start).total_seconds())
        bucket_offset = (offset // bucket_seconds) * bucket_seconds
        bucket = buckets.setdefault(
            bucket_offset,
            {
                "timestamp": (aligned_start + timedelta(seconds=bucket_offset))
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z"),
                "phase": _phase_for_offset(bucket_offset, windows),
                "http_reqs": 0.0,
                "durations": [],
                "failed": [],
                "vus": [],
            },
        )
        metric = point["metric"]
        value = float(point["value"])
        if metric == "http_reqs":
            bucket["http_reqs"] += value
        elif metric == "http_req_duration":
            bucket["durations"].append(value)
        elif metric == "http_req_failed":
            bucket["failed"].append(value)
        elif metric == "vus":
            bucket["vus"].append(value)

    rows = []
    for bucket_offset in sorted(buckets):
        bucket = buckets[bucket_offset]
        durations = bucket["durations"]
        failed = bucket["failed"]
        rows.append(
            {
                "timestamp": bucket["timestamp"],
                "phase": bucket["phase"],
                "rps": round(bucket["http_reqs"] / bucket_seconds, 6),
                "p95_latency_ms": _percentile_values(durations, 95),
                "p99_latency_ms": _percentile_values(durations, 99),
                "error_rate_percent": round((sum(failed) / len(failed) * 100) if failed else 0, 4),
                "virtual_users": max(bucket["vus"]) if bucket["vus"] else 0,
                "cpu_percent": 0,
                "memory_mb": 0,
                "cpu_throttling_percent": 0,
            }
        )
    return rows


def phase_windows(strategy: dict[str, Any]) -> list[dict[str, Any]]:
    windows = []
    cursor = 0
    for phase in strategy.get("phases", []):
        duration = _duration_seconds(str(phase.get("duration", "0s")))
        windows.append({"name": phase.get("name", "unknown"), "start_seconds": cursor, "end_seconds": cursor + duration})
        cursor += duration
    return windows


def _read_points(path: Path) -> list[dict[str, Any]]:
    points = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("type") != "Point":
            continue
        data = record.get("data", {})
        if "time" not in data or "value" not in data:
            continue
        points.append(
            {
                "metric": record.get("metric"),
                "time": _parse_time(data["time"]),
                "value": data["value"],
            }
        )
    return points


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _floor_time(value: datetime, bucket_seconds: int) -> datetime:
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    seconds = int((value - epoch).total_seconds())
    return epoch + timedelta(seconds=(seconds // bucket_seconds) * bucket_seconds)


def _phase_for_offset(offset_seconds: int, windows: list[dict[str, Any]]) -> str:
    for window in windows:
        if window["start_seconds"] <= offset_seconds < window["end_seconds"]:
            return window["name"]
    return windows[-1]["name"] if windows else "unknown"


def _duration_seconds(value: str) -> int:
    value = value.strip()
    if value.endswith("ms"):
        return max(1, math.ceil(float(value[:-2]) / 1000))
    if value.endswith("s"):
        return int(float(value[:-1]))
    if value.endswith("m"):
        return int(float(value[:-1]) * 60)
    if value.endswith("h"):
        return int(float(value[:-1]) * 3600)
    return int(float(value))


def _percentile_values(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = math.ceil((percentile / 100) * len(ordered)) - 1
    index = min(max(index, 0), len(ordered) - 1)
    return float(ordered[index])


def _percentile(metric: dict[str, Any], name: str) -> float:
    if "percentiles" in metric:
        return float(metric["percentiles"].get(name, 0))
    return float(metric.get(name, 0))


def _error_rate(metric: dict[str, Any]) -> float:
    if "rate" in metric:
        return float(metric["rate"])
    if "value" in metric:
        return float(metric["value"])
    fails = float(metric.get("fails", 0))
    passes = float(metric.get("passes", 0))
    total = fails + passes
    return fails / total if total else 0
