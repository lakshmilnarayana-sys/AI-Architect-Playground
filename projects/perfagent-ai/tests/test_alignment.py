from __future__ import annotations

import json

from perfagent.analyzers.alignment import align_k6_jsonl, phase_windows


def test_phase_windows_maps_strategy_stages_to_offsets():
    strategy = {
        "phases": [
            {"name": "warmup", "duration": "10s"},
            {"name": "baseline", "duration": "20s"},
            {"name": "stress", "duration": "30s"},
        ]
    }

    assert phase_windows(strategy) == [
        {"name": "warmup", "start_seconds": 0, "end_seconds": 10},
        {"name": "baseline", "start_seconds": 10, "end_seconds": 30},
        {"name": "stress", "start_seconds": 30, "end_seconds": 60},
    ]


def test_align_k6_jsonl_buckets_metrics_and_assigns_phases(tmp_path):
    jsonl = tmp_path / "k6_timeseries.jsonl"
    records = [
        _point("2026-06-13T10:00:01Z", "http_reqs", 1),
        _point("2026-06-13T10:00:02Z", "http_req_duration", 100),
        _point("2026-06-13T10:00:03Z", "http_req_duration", 300),
        _point("2026-06-13T10:00:03Z", "http_req_failed", 0),
        _point("2026-06-13T10:00:04Z", "vus", 5),
        _point("2026-06-13T10:00:12Z", "http_reqs", 1),
        _point("2026-06-13T10:00:13Z", "http_req_duration", 700),
        _point("2026-06-13T10:00:14Z", "http_req_failed", 1),
        _point("2026-06-13T10:00:14Z", "vus", 25),
    ]
    jsonl.write_text("\n".join(json.dumps(record) for record in records) + "\n")
    strategy = {
        "phases": [
            {"name": "baseline", "duration": "10s"},
            {"name": "stress", "duration": "10s"},
        ]
    }

    rows = align_k6_jsonl(jsonl, strategy, bucket_seconds=10)

    assert rows == [
        {
            "timestamp": "2026-06-13T10:00:00Z",
            "phase": "baseline",
            "rps": 0.1,
            "p95_latency_ms": 300.0,
            "p99_latency_ms": 300.0,
            "error_rate_percent": 0.0,
            "virtual_users": 5.0,
            "cpu_percent": 0,
            "memory_mb": 0,
            "cpu_throttling_percent": 0,
        },
        {
            "timestamp": "2026-06-13T10:00:10Z",
            "phase": "stress",
            "rps": 0.1,
            "p95_latency_ms": 700.0,
            "p99_latency_ms": 700.0,
            "error_rate_percent": 100.0,
            "virtual_users": 25.0,
            "cpu_percent": 0,
            "memory_mb": 0,
            "cpu_throttling_percent": 0,
        },
    ]


def _point(timestamp: str, metric: str, value: float) -> dict:
    return {
        "type": "Point",
        "metric": metric,
        "data": {
            "time": timestamp,
            "value": value,
            "tags": {},
        },
    }
