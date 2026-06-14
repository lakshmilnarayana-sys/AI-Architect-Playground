from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from perfagent.collectors.protocol_collectors import protocol_summary_to_aligned


def merge_worker_summaries(paths: list[Path]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    summaries = [_read_summary(path) for path in paths]
    total_count = sum(float(summary.get("metrics", {}).get("http_reqs", {}).get("count", 0) or 0) for summary in summaries)
    total_rate = sum(float(summary.get("metrics", {}).get("http_reqs", {}).get("rate", 0) or 0) for summary in summaries)
    failed_count = sum(_failed_count(summary) for summary in summaries)
    p95 = max((_metric(summary, "http_req_duration", "p(95)") for summary in summaries), default=0.0)
    p99 = max((_metric(summary, "http_req_duration", "p(99)") for summary in summaries), default=0.0)
    browser_metrics = _merge_browser_metrics(summaries)
    protocol_metrics = _merge_protocol_metrics(summaries)
    merged = {
        "metrics": {
            "http_reqs": {"count": total_count, "rate": total_rate},
            "http_req_duration": {"p(95)": p95, "p(99)": p99},
            "http_req_failed": {"rate": (failed_count / total_count) if total_count else 0.0},
            "checks": {"passes": max(total_count - failed_count, 0), "fails": failed_count},
            "iterations": {"count": total_count},
        },
        "worker_metadata": _worker_metadata(paths, summaries),
        "workers": [{"path": str(path), "summary": summary} for path, summary in zip(paths, summaries)],
    }
    if browser_metrics:
        merged["browser_metrics"] = browser_metrics
    if protocol_metrics:
        merged["protocol_metrics"] = protocol_metrics
    aligned = protocol_summary_to_aligned(merged, timestamp=_first_timestamp(summaries))
    for row in aligned:
        _add_protocol_metrics_to_row(row, protocol_metrics)
    return merged, aligned


def write_merged_worker_results(paths: list[Path], summary_path: Path, aligned_path: Path) -> dict[str, Any]:
    merged, aligned = merge_worker_summaries(paths)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n")
    aligned_path.parent.mkdir(parents=True, exist_ok=True)
    headers = sorted({key for row in aligned for key in row.keys()})
    aligned_path.write_text(",".join(headers) + "\n" + "\n".join(",".join(str(row.get(key, "")) for key in headers) for row in aligned) + "\n")
    return {"summary_path": str(summary_path), "aligned_path": str(aligned_path), "workers": len(paths)}


def _read_summary(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _metric(summary: dict[str, Any], metric: str, key: str) -> float:
    metric_value = summary.get("metrics", {}).get(metric, {})
    if key in metric_value:
        return float(metric_value.get(key, 0) or 0)
    return float(metric_value.get("percentiles", {}).get(key, 0) or 0)


def _failed_count(summary: dict[str, Any]) -> float:
    count = _metric(summary, "http_reqs", "count")
    rate = _metric(summary, "http_req_failed", "rate")
    return count * rate


def _first_timestamp(summaries: list[dict[str, Any]]) -> str:
    for summary in summaries:
        timestamp = summary.get("start_time") or summary.get("timestamp")
        if timestamp:
            return str(timestamp)
    return "1970-01-01T00:00:00Z"


def _worker_metadata(paths: list[Path], summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    workers = []
    for path, summary in zip(paths, summaries):
        metadata = summary.get("worker_metadata") or summary.get("worker") or summary.get("metadata") or {}
        row = {"path": str(path)}
        if isinstance(metadata, dict):
            row.update(metadata)
        workers.append(row)
    return workers


def _merge_browser_metrics(summaries: list[dict[str, Any]]) -> dict[str, float]:
    values: dict[str, list[float]] = {}
    for summary in summaries:
        browser_metrics = summary.get("browser_metrics", {})
        if not isinstance(browser_metrics, dict):
            continue
        for key, value in browser_metrics.items():
            if _is_number(value):
                values.setdefault(key, []).append(float(value))
    return {key: round(sum(items) / len(items), 4) for key, items in sorted(values.items()) if items}


def _merge_protocol_metrics(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for summary in summaries:
        metrics = {}
        protocol_metrics = summary.get("protocol_metrics", {})
        if isinstance(protocol_metrics, dict):
            metrics.update(protocol_metrics)
        for key in ("grpc_status", "websocket_messages", "connection_errors"):
            if key in summary:
                metrics[key] = summary[key]
        _merge_protocol_values(merged, metrics)
    return merged


def _merge_protocol_values(merged: dict[str, Any], metrics: dict[str, Any]) -> None:
    for key, value in metrics.items():
        if key == "grpc_status":
            status_counts = _grpc_status_counts(value)
            if not status_counts:
                continue
            current = merged.setdefault("grpc_status", {})
            for status, count in status_counts.items():
                current[status] = current.get(status, 0) + count
        elif _is_number(value):
            merged[key] = merged.get(key, 0) + float(value)


def _grpc_status_counts(value: Any) -> dict[str, int]:
    if isinstance(value, dict):
        return {str(status): int(count) for status, count in sorted(value.items()) if _is_number(count)}
    if isinstance(value, str) and value:
        return {value: 1}
    return {}


def _add_protocol_metrics_to_row(row: dict[str, Any], protocol_metrics: dict[str, Any]) -> None:
    for key, value in protocol_metrics.items():
        if key == "grpc_status" and isinstance(value, dict):
            row[key] = json.dumps(value, sort_keys=True, separators=(",", ":"))
        else:
            row[key] = int(value) if isinstance(value, float) and value.is_integer() else value


def _is_number(value: Any) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False
