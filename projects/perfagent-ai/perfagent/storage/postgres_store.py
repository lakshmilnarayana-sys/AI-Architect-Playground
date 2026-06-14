from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from perfagent.storage.run_store import normalize_artifacts, normalize_findings


class PostgresRunStore:
    def __init__(self, dsn: str, *, connect: Callable[..., Any] | None = None) -> None:
        self.dsn = dsn
        self._connect = connect or _load_psycopg_connect()
        self._init_schema()

    def record_run(self, run: dict[str, Any]) -> None:
        created_at = run.get("created_at") or datetime.now(UTC).isoformat()
        features = run.get("features", {})
        with self._connect(self.dsn) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO perf_runs (
                      run_id, service_name, created_at, release_decision,
                      stable_rps, max_p95_latency_ms, max_error_rate_percent,
                      report_html_path, features_json, summary_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
                    ON CONFLICT (run_id) DO UPDATE SET
                      service_name = EXCLUDED.service_name,
                      created_at = EXCLUDED.created_at,
                      release_decision = EXCLUDED.release_decision,
                      stable_rps = EXCLUDED.stable_rps,
                      max_p95_latency_ms = EXCLUDED.max_p95_latency_ms,
                      max_error_rate_percent = EXCLUDED.max_error_rate_percent,
                      report_html_path = EXCLUDED.report_html_path,
                      features_json = EXCLUDED.features_json,
                      summary_json = EXCLUDED.summary_json
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
                cursor.execute(
                    """
                    INSERT INTO perf_features (
                      run_id, stable_rps, peak_rps, max_p95_latency_ms, max_p99_latency_ms,
                      max_error_rate_percent, estimated_capacity_rps, breaking_point_rps,
                      first_slo_breach_phase, features_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (run_id) DO UPDATE SET
                      stable_rps = EXCLUDED.stable_rps,
                      peak_rps = EXCLUDED.peak_rps,
                      max_p95_latency_ms = EXCLUDED.max_p95_latency_ms,
                      max_p99_latency_ms = EXCLUDED.max_p99_latency_ms,
                      max_error_rate_percent = EXCLUDED.max_error_rate_percent,
                      estimated_capacity_rps = EXCLUDED.estimated_capacity_rps,
                      breaking_point_rps = EXCLUDED.breaking_point_rps,
                      first_slo_breach_phase = EXCLUDED.first_slo_breach_phase,
                      features_json = EXCLUDED.features_json
                    """,
                    (
                        run["run_id"],
                        float(features.get("stable_rps", 0) or 0),
                        float(features.get("peak_rps", 0) or 0),
                        float(features.get("max_p95_latency_ms", 0) or 0),
                        float(features.get("max_p99_latency_ms", 0) or 0),
                        float(features.get("max_error_rate_percent", 0) or 0),
                        float(features.get("estimated_capacity_rps", 0) or 0),
                        float(features.get("breaking_point_rps", 0) or 0),
                        features.get("first_slo_breach_phase"),
                        json.dumps(features, sort_keys=True),
                    ),
                )
                self._record_artifacts(cursor, run["run_id"], run.get("artifacts") or [])
                self._record_timeseries(cursor, run["run_id"], run.get("timeseries") or run.get("aligned_timeseries") or [])
                self._record_findings(cursor, run["run_id"], run.get("findings") or [])

    def record_artifacts(self, run_id: str, artifacts: Any) -> int:
        with self._connect(self.dsn) as conn:
            with conn.cursor() as cursor:
                return self._record_artifacts(cursor, run_id, artifacts)

    def record_timeseries(self, run_id: str, samples: list[dict[str, Any]]) -> int:
        with self._connect(self.dsn) as conn:
            with conn.cursor() as cursor:
                return self._record_timeseries(cursor, run_id, samples)

    def record_findings(self, run_id: str, findings: list[Any]) -> int:
        with self._connect(self.dsn) as conn:
            with conn.cursor() as cursor:
                return self._record_findings(cursor, run_id, findings)

    def list_runs(self, service_name: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM perf_runs"
        params: tuple[Any, ...] = ()
        if service_name:
            query += " WHERE service_name = %s"
            params = (service_name,)
        query += " ORDER BY created_at DESC"
        with self._connect(self.dsn) as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                columns = [column[0] for column in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def apply_retention(self, *, retention_days: int, now: datetime | None = None) -> int:
        now = now or datetime.now(UTC)
        cutoff = now - timedelta(days=retention_days)
        with self._connect(self.dsn) as conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM perf_runs WHERE created_at < %s", (cutoff.isoformat(),))
                return int(cursor.rowcount or 0)

    def _init_schema(self) -> None:
        with self._connect(self.dsn) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS perf_runs (
                      run_id TEXT PRIMARY KEY,
                      service_name TEXT NOT NULL,
                      created_at TIMESTAMPTZ NOT NULL,
                      release_decision TEXT NOT NULL,
                      stable_rps DOUBLE PRECISION NOT NULL,
                      max_p95_latency_ms DOUBLE PRECISION NOT NULL,
                      max_error_rate_percent DOUBLE PRECISION NOT NULL,
                      report_html_path TEXT NOT NULL,
                      features_json JSONB NOT NULL,
                      summary_json JSONB NOT NULL
                    )
                    """
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_perf_runs_service_created ON perf_runs(service_name, created_at)"
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS perf_features (
                      run_id TEXT PRIMARY KEY REFERENCES perf_runs(run_id) ON DELETE CASCADE,
                      stable_rps DOUBLE PRECISION NOT NULL,
                      peak_rps DOUBLE PRECISION NOT NULL,
                      max_p95_latency_ms DOUBLE PRECISION NOT NULL,
                      max_p99_latency_ms DOUBLE PRECISION NOT NULL,
                      max_error_rate_percent DOUBLE PRECISION NOT NULL,
                      estimated_capacity_rps DOUBLE PRECISION NOT NULL,
                      breaking_point_rps DOUBLE PRECISION NOT NULL,
                      first_slo_breach_phase TEXT,
                      features_json JSONB NOT NULL
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS perf_artifacts (
                      artifact_id BIGSERIAL PRIMARY KEY,
                      run_id TEXT NOT NULL REFERENCES perf_runs(run_id) ON DELETE CASCADE,
                      artifact_type TEXT NOT NULL,
                      artifact_path TEXT NOT NULL,
                      content_type TEXT,
                      size_bytes BIGINT,
                      checksum TEXT,
                      payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                      created_at TIMESTAMPTZ DEFAULT now(),
                      UNIQUE(run_id, artifact_type, artifact_path)
                    )
                    """
                )
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_perf_artifacts_run ON perf_artifacts(run_id)")
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS perf_regression_results (
                      result_id BIGSERIAL PRIMARY KEY,
                      current_run_id TEXT NOT NULL,
                      baseline_run_id TEXT,
                      regression_detected BOOLEAN NOT NULL,
                      findings_json JSONB NOT NULL,
                      created_at TIMESTAMPTZ DEFAULT now()
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS perf_findings (
                      finding_id BIGSERIAL PRIMARY KEY,
                      run_id TEXT NOT NULL,
                      finding_type TEXT NOT NULL,
                      severity TEXT NOT NULL,
                      evidence TEXT NOT NULL,
                      recommendation TEXT,
                      source TEXT,
                      payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                      created_at TIMESTAMPTZ DEFAULT now()
                    )
                    """
                )
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_perf_findings_run ON perf_findings(run_id)")
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS perf_timeseries (
                      run_id TEXT NOT NULL,
                      timestamp TIMESTAMPTZ NOT NULL,
                      phase TEXT,
                      rps DOUBLE PRECISION,
                      p95_latency_ms DOUBLE PRECISION,
                      p99_latency_ms DOUBLE PRECISION,
                      error_rate_percent DOUBLE PRECISION,
                      virtual_users DOUBLE PRECISION,
                      cpu_percent DOUBLE PRECISION,
                      memory_mb DOUBLE PRECISION,
                      payload_json JSONB,
                      PRIMARY KEY (run_id, timestamp, phase)
                    )
                    """
                )
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_perf_timeseries_run ON perf_timeseries(run_id, timestamp)")
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS perf_dependencies (
                      dependency_id BIGSERIAL PRIMARY KEY,
                      run_id TEXT NOT NULL,
                      dependency_name TEXT NOT NULL,
                      dependency_type TEXT,
                      metric_name TEXT,
                      metric_value DOUBLE PRECISION,
                      payload_json JSONB,
                      created_at TIMESTAMPTZ DEFAULT now()
                    )
                    """
                )

    def _record_artifacts(self, cursor: Any, run_id: str, artifacts: Any) -> int:
        rows = normalize_artifacts(artifacts)
        for artifact in rows:
            cursor.execute(
                """
                INSERT INTO perf_artifacts (
                  run_id, artifact_type, artifact_path, content_type,
                  size_bytes, checksum, payload_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (run_id, artifact_type, artifact_path) DO UPDATE SET
                  content_type = EXCLUDED.content_type,
                  size_bytes = EXCLUDED.size_bytes,
                  checksum = EXCLUDED.checksum,
                  payload_json = EXCLUDED.payload_json
                """,
                (
                    run_id,
                    artifact["artifact_type"],
                    artifact["artifact_path"],
                    artifact.get("content_type"),
                    artifact.get("size_bytes"),
                    artifact.get("checksum"),
                    json.dumps(artifact.get("payload", artifact), sort_keys=True, default=str),
                ),
            )
        return len(rows)

    def _record_timeseries(self, cursor: Any, run_id: str, samples: list[dict[str, Any]]) -> int:
        for sample in samples:
            timestamp = sample.get("timestamp") or sample.get("time") or sample.get("ts") or datetime.now(UTC).isoformat()
            phase = str(sample.get("phase") or "")
            cursor.execute(
                """
                INSERT INTO perf_timeseries (
                  run_id, timestamp, phase, rps, p95_latency_ms, p99_latency_ms,
                  error_rate_percent, virtual_users, cpu_percent, memory_mb, payload_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (run_id, timestamp, phase) DO UPDATE SET
                  rps = EXCLUDED.rps,
                  p95_latency_ms = EXCLUDED.p95_latency_ms,
                  p99_latency_ms = EXCLUDED.p99_latency_ms,
                  error_rate_percent = EXCLUDED.error_rate_percent,
                  virtual_users = EXCLUDED.virtual_users,
                  cpu_percent = EXCLUDED.cpu_percent,
                  memory_mb = EXCLUDED.memory_mb,
                  payload_json = EXCLUDED.payload_json
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

    def _record_findings(self, cursor: Any, run_id: str, findings: list[Any]) -> int:
        rows = normalize_findings(findings)
        for finding in rows:
            cursor.execute(
                """
                INSERT INTO perf_findings (
                  run_id, finding_type, severity, evidence, recommendation,
                  source, payload_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    run_id,
                    finding["finding_type"],
                    finding["severity"],
                    finding["evidence"],
                    finding.get("recommendation"),
                    finding.get("source"),
                    json.dumps(finding.get("payload", finding), sort_keys=True, default=str),
                ),
            )
        return len(rows)


def _load_psycopg_connect() -> Callable[..., Any]:
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - depends on optional environment
        raise RuntimeError("Postgres storage requires psycopg. Install perfagent-ai[postgres].") from exc
    return psycopg.connect


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
