from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


class RunStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def record_run(self, run: dict[str, Any]) -> None:
        created_at = run.get("created_at") or datetime.now(UTC).isoformat()
        features = run.get("features", {})
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO perf_runs (
                  run_id, service_name, created_at, release_decision,
                  stable_rps, max_p95_latency_ms, max_error_rate_percent,
                  report_html_path, features_json, summary_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run["run_id"],
                    run["service_name"],
                    created_at,
                    run.get("release_decision", "UNKNOWN"),
                    float(features.get("stable_rps", 0) or 0),
                    float(features.get("max_p95_latency_ms", 0) or 0),
                    float(features.get("max_error_rate_percent", 0) or 0),
                    run.get("report_html_path", ""),
                    json.dumps(features, sort_keys=True),
                    json.dumps(run, sort_keys=True, default=str),
                ),
            )

    def list_runs(self, service_name: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM perf_runs"
        params: tuple[Any, ...] = ()
        if service_name:
            query += " WHERE service_name = ?"
            params = (service_name,)
        query += " ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_row_to_dict(row) for row in rows]

    def latest_run(self, service_name: str) -> dict[str, Any] | None:
        runs = self.list_runs(service_name)
        return runs[0] if runs else None

    def apply_retention(self, *, retention_days: int, now: datetime | None = None) -> int:
        now = now or datetime.now(UTC)
        cutoff = now - timedelta(days=retention_days)
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM perf_runs WHERE created_at < ?", (cutoff.isoformat(),))
            return cursor.rowcount

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS perf_runs (
                  run_id TEXT PRIMARY KEY,
                  service_name TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  release_decision TEXT NOT NULL,
                  stable_rps REAL NOT NULL,
                  max_p95_latency_ms REAL NOT NULL,
                  max_error_rate_percent REAL NOT NULL,
                  report_html_path TEXT NOT NULL,
                  features_json TEXT NOT NULL,
                  summary_json TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_perf_runs_service_created ON perf_runs(service_name, created_at)")


def compare_to_latest_baseline(
    store: RunStore,
    service_name: str,
    current_features: dict[str, Any],
    *,
    max_p95_regression_percent: float = 20,
    max_error_rate_delta_percent: float = 0.5,
) -> dict[str, Any]:
    baseline = store.latest_run(service_name)
    if not baseline:
        return {"regression_detected": False, "baseline_run_id": None, "findings": ["no baseline run available"]}
    baseline_features = json.loads(baseline["features_json"])
    findings: list[str] = []
    baseline_p95 = float(baseline_features.get("max_p95_latency_ms", 0) or 0)
    current_p95 = float(current_features.get("max_p95_latency_ms", 0) or 0)
    if baseline_p95:
        p95_delta_percent = round(((current_p95 - baseline_p95) / baseline_p95) * 100, 4)
        if p95_delta_percent > max_p95_regression_percent:
            findings.append(f"p95 latency regressed by {round(p95_delta_percent, 1)}%")
    baseline_error = float(baseline_features.get("max_error_rate_percent", 0) or 0)
    current_error = float(current_features.get("max_error_rate_percent", 0) or 0)
    error_delta = round(current_error - baseline_error, 4)
    if error_delta > max_error_rate_delta_percent:
        findings.append(f"error rate increased by {round(error_delta, 1)} percentage points")
    return {
        "regression_detected": bool(findings),
        "baseline_run_id": baseline["run_id"],
        "findings": findings,
    }


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}
