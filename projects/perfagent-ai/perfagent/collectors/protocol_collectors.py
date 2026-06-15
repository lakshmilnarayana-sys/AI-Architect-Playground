from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def run_protocol_script(
    *,
    tool: str,
    script_path: Path,
    summary_path: Path,
    execution_log_path: Path,
    duration_seconds: int,
    concurrency: int,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    args = [
        sys.executable,
        str(script_path),
        "--duration-seconds",
        str(duration_seconds),
    ]
    if tool == "websocket":
        args.extend(["--connections", str(concurrency)])
    else:
        args.extend(["--concurrency", str(concurrency)])

    start = datetime.now(UTC)
    started = time.perf_counter()
    completed = subprocess.run(args, text=True, capture_output=True, check=False)
    elapsed_seconds = max(time.perf_counter() - started, 0.001)
    end = datetime.now(UTC)

    parsed = _parse_last_json_line(completed.stdout)
    summary = protocol_result_to_summary(parsed, elapsed_seconds=elapsed_seconds)
    execution_result = {
        "tool": tool,
        "exit_code": completed.returncode,
        "command": args,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "summary_path": str(summary_path),
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
    }
    if completed.returncode != 0:
        execution_result["error"] = "protocol load script exited non-zero"
    aligned = protocol_summary_to_aligned(summary, timestamp=start.isoformat().replace("+00:00", "Z"))

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    execution_log_path.parent.mkdir(parents=True, exist_ok=True)
    execution_log_path.write_text(
        "COMMAND: "
        + " ".join(args)
        + "\n\nSTDOUT:\n"
        + _truncate(completed.stdout)
        + "\nSTDERR:\n"
        + _truncate(completed.stderr)
    )
    return execution_result, summary, aligned


def protocol_result_to_summary(result: Any, *, elapsed_seconds: float) -> dict[str, Any]:
    rows = result if isinstance(result, list) else [result]
    requests = sum(int(row.get("requests", 0) or 0) for row in rows if isinstance(row, dict))
    errors = sum(int(row.get("errors", 0) or 0) for row in rows if isinstance(row, dict))
    latencies: list[float] = []
    browser_metrics: list[dict[str, Any]] = []
    browser_artifacts: list[dict[str, Any]] = []
    protocol_metrics: dict[str, Any] = {}
    for row in rows:
        if isinstance(row, dict):
            latencies.extend(float(value) for value in row.get("latencies_ms", []) if _is_number(value))
            raw_browser_metrics = row.get("browser_metrics", [])
            if isinstance(raw_browser_metrics, dict):
                browser_metrics.append(raw_browser_metrics)
            else:
                browser_metrics.extend(item for item in raw_browser_metrics if isinstance(item, dict))
            raw_browser_artifacts = row.get("browser_artifacts", [])
            if isinstance(raw_browser_artifacts, dict):
                browser_artifacts.append(raw_browser_artifacts)
            else:
                browser_artifacts.extend(item for item in raw_browser_artifacts if isinstance(item, dict))
            _merge_protocol_metrics(protocol_metrics, row.get("protocol_metrics", {}))
            _merge_protocol_metrics(
                protocol_metrics,
                {key: row[key] for key in ("grpc_status", "websocket_messages", "connection_errors") if key in row},
            )
    p95 = _percentile(latencies, 95)
    p99 = _percentile(latencies, 99)
    failed_rate = errors / requests if requests else 0.0
    summary = {
        "metrics": {
            "http_reqs": {"count": requests, "rate": requests / elapsed_seconds},
            "http_req_duration": {"avg": sum(latencies) / len(latencies) if latencies else 0, "p(95)": p95, "p(99)": p99},
            "http_req_failed": {"rate": failed_rate, "passes": errors, "fails": max(requests - errors, 0)},
            "checks": {"passes": max(requests - errors, 0), "fails": errors},
            "iterations": {"count": requests},
        }
    }
    if browser_metrics:
        summary["browser_metrics"] = _average_browser_metrics(browser_metrics)
    if browser_artifacts:
        summary["browser_artifacts"] = browser_artifacts
    if protocol_metrics:
        summary["protocol_metrics"] = protocol_metrics
    return summary


def protocol_summary_to_aligned(summary: dict[str, Any], *, timestamp: str) -> list[dict[str, Any]]:
    metrics = summary.get("metrics", {})
    row = {
        "timestamp": timestamp,
        "phase": "protocol",
        "rps": float(metrics.get("http_reqs", {}).get("rate", 0) or 0),
        "p95_latency_ms": float(metrics.get("http_req_duration", {}).get("p(95)", 0) or 0),
        "p99_latency_ms": float(metrics.get("http_req_duration", {}).get("p(99)", 0) or 0),
        "error_rate_percent": float(metrics.get("http_req_failed", {}).get("rate", 0) or 0) * 100,
        "virtual_users": 0,
    }
    for key, value in summary.get("browser_metrics", {}).items():
        row[f"browser_{key}"] = value
    for key, value in summary.get("protocol_metrics", {}).items():
        row[key] = json.dumps(value, sort_keys=True, separators=(",", ":")) if isinstance(value, dict) else value
    return [row]


def duration_to_seconds(value: str) -> int:
    value = str(value or "60s").strip().lower()
    if value.endswith("ms"):
        return max(1, int(float(value[:-2]) / 1000))
    if value.endswith("s"):
        return max(1, int(float(value[:-1])))
    if value.endswith("m"):
        return max(1, int(float(value[:-1]) * 60))
    if value.endswith("h"):
        return max(1, int(float(value[:-1]) * 3600))
    return max(1, int(float(value)))


def _parse_last_json_line(stdout: str) -> Any:
    for line in reversed(stdout.splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        return json.loads(stripped)
    return {}


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    index = min(max(int(round((percentile / 100) * len(values) + 0.5)) - 1, 0), len(values) - 1)
    return sorted(values)[index]


def _is_number(value: Any) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _merge_protocol_metrics(target: dict[str, Any], source: Any) -> None:
    if not isinstance(source, dict):
        return
    for key, value in source.items():
        if key == "grpc_status" and isinstance(value, dict):
            status_counts = target.setdefault("grpc_status", {})
            for status, count in value.items():
                if _is_number(count):
                    status_counts[str(status)] = status_counts.get(str(status), 0) + int(count)
        elif _is_number(value):
            target[key] = target.get(key, 0) + float(value)


def _truncate(value: str, limit: int = 20000) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + f"\n... truncated {len(value) - limit} characters ..."


def _average_browser_metrics(items: list[dict[str, Any]]) -> dict[str, float]:
    keys = sorted({key for item in items for key in item.keys() if _is_number(item.get(key))})
    averaged: dict[str, float] = {}
    for key in keys:
        values = [float(item[key]) for item in items if _is_number(item.get(key))]
        averaged[key] = round(sum(values) / len(values), 4) if values else 0.0
    return averaged
