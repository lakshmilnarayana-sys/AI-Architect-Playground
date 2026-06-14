from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


def load_external_results(tool: str, result_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    normalized = tool.lower()
    if normalized == "locust":
        return load_locust_results(result_path)
    if normalized == "jmeter":
        return load_jmeter_results(result_path)
    raise ValueError(f"Unsupported external performance tool: {tool}")


def load_locust_results(stats_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows = list(csv.DictReader(stats_path.read_text().splitlines()))
    aggregate = _locust_aggregate(rows)
    request_count = int(_number(aggregate.get("Request Count")))
    failure_count = int(_number(aggregate.get("Failure Count")))
    rps = _number(aggregate.get("Requests/s"))
    p95 = _number(aggregate.get("95%"))
    p99 = _number(aggregate.get("99%"))
    error_rate = (failure_count / request_count * 100) if request_count else 0.0
    aligned = _load_locust_history(stats_path) or [_single_external_row(rps, p95, p99, error_rate)]
    return _summary(request_count, failure_count, rps, p95, p99), aligned


def load_jmeter_results(jtl_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    text = jtl_path.read_text()
    samples = _load_jmeter_csv(text)
    if not samples:
        samples = _load_jmeter_xml(text)
    elapsed = sorted(_number(sample.get("elapsed")) for sample in samples)
    request_count = len(samples)
    failure_count = sum(1 for sample in samples if str(sample.get("success", "")).lower() == "false")
    duration_seconds = _duration_seconds(samples)
    rps = request_count / duration_seconds if duration_seconds else 0.0
    p95 = _percentile(elapsed, 95)
    p99 = _percentile(elapsed, 99)
    error_rate = (failure_count / request_count * 100) if request_count else 0.0
    timestamp = _first_timestamp(samples)
    aligned = _bucket_jmeter_samples(samples)
    return _summary(request_count, failure_count, rps, p95, p99), aligned


def _summary(request_count: int, failure_count: int, rps: float, p95: float, p99: float) -> dict[str, Any]:
    return {
        "metrics": {
            "http_reqs": {"count": request_count, "rate": round(rps, 4)},
            "http_req_duration": {"percentiles": {"p(95)": p95, "p(99)": p99}},
            "http_req_failed": {"fails": failure_count, "passes": max(request_count - failure_count, 0)},
        }
    }


def _locust_aggregate(rows: list[dict[str, str]]) -> dict[str, str]:
    for row in rows:
        if row.get("Name") in {"Aggregated", "Total"}:
            return row
    return rows[-1] if rows else {}


def _load_locust_history(stats_path: Path) -> list[dict[str, Any]]:
    history_path = stats_path.with_name(stats_path.stem.replace("_stats", "") + "_stats_history.csv")
    if not history_path.exists():
        return []
    history = list(csv.DictReader(history_path.read_text().splitlines()))
    aligned: list[dict[str, Any]] = []
    for row in history:
        if row.get("Name") not in {"Aggregated", "Total", ""}:
            continue
        rps = _number(row.get("Requests/s"))
        failures = _number(row.get("Failures/s"))
        error_rate = failures / rps * 100 if rps else 0.0
        aligned.append(
            {
                "timestamp": _format_epoch_seconds(_number(row.get("Timestamp"))),
                "phase": "external",
                "rps": rps,
                "p95_latency_ms": _number(row.get("95%")),
                "p99_latency_ms": _number(row.get("99%")),
                "error_rate_percent": round(error_rate, 4),
                "virtual_users": int(_number(row.get("User Count"))),
            }
        )
    return aligned


def _single_external_row(rps: float, p95: float, p99: float, error_rate: float) -> dict[str, Any]:
    return {
        "timestamp": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "phase": "external",
        "rps": rps,
        "p95_latency_ms": p95,
        "p99_latency_ms": p99,
        "error_rate_percent": round(error_rate, 4),
        "virtual_users": 0,
    }


def _bucket_jmeter_samples(samples: list[dict[str, str]], bucket_seconds: int = 10) -> list[dict[str, Any]]:
    buckets: dict[int, list[dict[str, str]]] = {}
    for sample in samples:
        timestamp = int(_number(sample.get("timeStamp")) / 1000)
        bucket = timestamp - (timestamp % bucket_seconds)
        buckets.setdefault(bucket, []).append(sample)
    aligned: list[dict[str, Any]] = []
    for bucket, bucket_samples in sorted(buckets.items()):
        elapsed = sorted(_number(sample.get("elapsed")) for sample in bucket_samples)
        failures = sum(1 for sample in bucket_samples if str(sample.get("success", "")).lower() == "false")
        count = len(bucket_samples)
        aligned.append(
            {
                "timestamp": _format_epoch_seconds(bucket),
                "phase": "external",
                "rps": round(count / bucket_seconds, 4),
                "p95_latency_ms": _percentile(elapsed, 95),
                "p99_latency_ms": _percentile(elapsed, 99),
                "error_rate_percent": round((failures / count * 100) if count else 0.0, 4),
                "virtual_users": 0,
            }
        )
    return aligned or [_single_external_row(0, 0, 0, 0)]


def _load_jmeter_csv(text: str) -> list[dict[str, str]]:
    try:
        rows = list(csv.DictReader(text.splitlines()))
    except csv.Error:
        return []
    if not rows or "elapsed" not in rows[0]:
        return []
    return rows


def _load_jmeter_xml(text: str) -> list[dict[str, str]]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    samples: list[dict[str, str]] = []
    for sample in root.iter():
        if sample.tag not in {"httpSample", "sample"}:
            continue
        samples.append(
            {
                "timeStamp": sample.attrib.get("ts", ""),
                "elapsed": sample.attrib.get("t", "0"),
                "success": sample.attrib.get("s", "false"),
            }
        )
    return samples


def _duration_seconds(samples: list[dict[str, str]]) -> float:
    timestamps = [_number(sample.get("timeStamp")) for sample in samples if sample.get("timeStamp")]
    if len(timestamps) < 2:
        return 1.0 if samples else 0.0
    return max((max(timestamps) - min(timestamps)) / 1000, 1.0)


def _first_timestamp(samples: list[dict[str, str]]) -> str:
    values = [_number(sample.get("timeStamp")) for sample in samples if sample.get("timeStamp")]
    if not values:
        return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return datetime.fromtimestamp(min(values) / 1000, tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _format_epoch_seconds(value: float) -> str:
    return datetime.fromtimestamp(value, tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    index = min(len(values) - 1, max(0, round((percentile / 100) * (len(values) - 1))))
    return values[index]


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
