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
    merged = {
        "metrics": {
            "http_reqs": {"count": total_count, "rate": total_rate},
            "http_req_duration": {"p(95)": p95, "p(99)": p99},
            "http_req_failed": {"rate": (failed_count / total_count) if total_count else 0.0},
            "checks": {"passes": max(total_count - failed_count, 0), "fails": failed_count},
            "iterations": {"count": total_count},
        },
        "workers": [{"path": str(path), "summary": summary} for path, summary in zip(paths, summaries)],
    }
    aligned = protocol_summary_to_aligned(merged, timestamp=_first_timestamp(summaries))
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
