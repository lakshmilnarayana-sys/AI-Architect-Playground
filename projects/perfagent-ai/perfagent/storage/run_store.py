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
            self._record_artifacts(conn, run["run_id"], run.get("artifacts") or [])
            self._record_timeseries(conn, run["run_id"], run.get("timeseries") or run.get("aligned_timeseries") or [])
            self._record_findings(conn, run["run_id"], run.get("findings") or [])

    def record_artifacts(self, run_id: str, artifacts: Any) -> int:
        with self._connect() as conn:
            return self._record_artifacts(conn, run_id, artifacts)

    def record_timeseries(self, run_id: str, samples: list[dict[str, Any]]) -> int:
        with self._connect() as conn:
            return self._record_timeseries(conn, run_id, samples)

    def record_findings(self, run_id: str, findings: list[Any]) -> int:
        with self._connect() as conn:
            return self._record_findings(conn, run_id, findings)

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

    def latest_run(self, service_name: str, *, exclude_run_id: str | None = None) -> dict[str, Any] | None:
        runs = [run for run in self.list_runs(service_name) if run["run_id"] != exclude_run_id]
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS perf_artifacts (
                  artifact_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  run_id TEXT NOT NULL,
                  artifact_type TEXT NOT NULL,
                  artifact_path TEXT NOT NULL,
                  content_type TEXT,
                  size_bytes INTEGER,
                  checksum TEXT,
                  payload_json TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  UNIQUE(run_id, artifact_type, artifact_path)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_perf_artifacts_run ON perf_artifacts(run_id)")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS perf_timeseries (
                  run_id TEXT NOT NULL,
                  timestamp TEXT NOT NULL,
                  phase TEXT NOT NULL,
                  rps REAL,
                  p95_latency_ms REAL,
                  p99_latency_ms REAL,
                  error_rate_percent REAL,
                  virtual_users REAL,
                  cpu_percent REAL,
                  memory_mb REAL,
                  payload_json TEXT NOT NULL,
                  PRIMARY KEY (run_id, timestamp, phase)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_perf_timeseries_run ON perf_timeseries(run_id, timestamp)")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS perf_findings (
                  finding_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  run_id TEXT NOT NULL,
                  finding_type TEXT NOT NULL,
                  severity TEXT NOT NULL,
                  evidence TEXT NOT NULL,
                  recommendation TEXT,
                  source TEXT,
                  payload_json TEXT NOT NULL,
                  created_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_perf_findings_run ON perf_findings(run_id)")

    def _record_artifacts(self, conn: sqlite3.Connection, run_id: str, artifacts: Any) -> int:
        rows = normalize_artifacts(artifacts)
        for artifact in rows:
            conn.execute(
                """
                INSERT OR IGNORE INTO perf_artifacts (
                  run_id, artifact_type, artifact_path, content_type, size_bytes,
                  checksum, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    artifact["artifact_type"],
                    artifact["artifact_path"],
                    artifact.get("content_type"),
                    artifact.get("size_bytes"),
                    artifact.get("checksum"),
                    json.dumps(artifact.get("payload", artifact), sort_keys=True, default=str),
                    datetime.now(UTC).isoformat(),
                ),
            )
        return len(rows)

    def _record_timeseries(self, conn: sqlite3.Connection, run_id: str, samples: list[dict[str, Any]]) -> int:
        for sample in samples:
            timestamp = str(sample.get("timestamp") or sample.get("time") or sample.get("ts") or datetime.now(UTC).isoformat())
            phase = str(sample.get("phase") or "")
            conn.execute(
                """
                INSERT OR REPLACE INTO perf_timeseries (
                  run_id, timestamp, phase, rps, p95_latency_ms, p99_latency_ms,
                  error_rate_percent, virtual_users, cpu_percent, memory_mb, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    timestamp,
                    phase,
                    _optional_float(sample.get("rps")),
                    _optional_float(sample.get("p95_latency_ms") or sample.get("p95")),
                    _optional_float(sample.get("p99_latency_ms") or sample.get("p99")),
                    _optional_float(sample.get("error_rate_percent") or sample.get("error_rate")),
                    _optional_float(sample.get("virtual_users") or sample.get("vus")),
                    _optional_float(sample.get("cpu_percent") or sample.get("cpu")),
                    _optional_float(sample.get("memory_mb") or sample.get("memory")),
                    json.dumps(sample, sort_keys=True, default=str),
                ),
            )
        return len(samples)

    def _record_findings(self, conn: sqlite3.Connection, run_id: str, findings: list[Any]) -> int:
        rows = normalize_findings(findings)
        for finding in rows:
            conn.execute(
                """
                INSERT INTO perf_findings (
                  run_id, finding_type, severity, evidence, recommendation,
                  source, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    finding["finding_type"],
                    finding["severity"],
                    finding["evidence"],
                    finding.get("recommendation"),
                    finding.get("source"),
                    json.dumps(finding.get("payload", finding), sort_keys=True, default=str),
                    datetime.now(UTC).isoformat(),
                ),
            )
        return len(rows)


def compare_to_latest_baseline(
    store: RunStore,
    service_name: str,
    current_features: dict[str, Any],
    *,
    exclude_run_id: str | None = None,
    max_p95_regression_percent: float = 20,
    max_error_rate_delta_percent: float = 0.5,
) -> dict[str, Any]:
    baseline = store.latest_run(service_name, exclude_run_id=exclude_run_id)
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


def normalize_artifacts(artifacts: Any) -> list[dict[str, Any]]:
    if isinstance(artifacts, dict):
        iterable = [
            {"type": artifact_type, **value} if isinstance(value, dict) else {"type": artifact_type, "path": value}
            for artifact_type, value in artifacts.items()
        ]
    else:
        iterable = list(artifacts or [])
    rows: list[dict[str, Any]] = []
    for item in iterable:
        if isinstance(item, dict):
            artifact_type = item.get("artifact_type") or item.get("type") or item.get("name") or "artifact"
            artifact_path = item.get("artifact_path") or item.get("path") or item.get("uri") or item.get("url") or ""
            if not artifact_path:
                continue
            rows.append(
                {
                    "artifact_type": str(artifact_type),
                    "artifact_path": str(artifact_path),
                    "content_type": item.get("content_type"),
                    "size_bytes": item.get("size_bytes") or item.get("size"),
                    "checksum": item.get("checksum"),
                    "payload": item,
                }
            )
        elif item:
            rows.append(
                {
                    "artifact_type": "artifact",
                    "artifact_path": str(item),
                    "content_type": None,
                    "size_bytes": None,
                    "checksum": None,
                    "payload": {"path": str(item)},
                }
            )
    return rows


def normalize_findings(findings: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in findings:
        if isinstance(item, dict):
            evidence = item.get("evidence") or item.get("message") or item.get("summary") or item.get("finding") or ""
            rows.append(
                {
                    "finding_type": str(item.get("finding_type") or item.get("type") or "finding"),
                    "severity": str(item.get("severity") or "info"),
                    "evidence": str(evidence),
                    "recommendation": item.get("recommendation"),
                    "source": item.get("source"),
                    "payload": item,
                }
            )
        elif item:
            rows.append(
                {
                    "finding_type": "finding",
                    "severity": "info",
                    "evidence": str(item),
                    "recommendation": None,
                    "source": None,
                    "payload": {"evidence": str(item)},
                }
            )
    return rows


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
