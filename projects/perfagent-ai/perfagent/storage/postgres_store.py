from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, Callable


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


def _load_psycopg_connect() -> Callable[..., Any]:
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - depends on optional environment
        raise RuntimeError("Postgres storage requires psycopg. Install perfagent-ai[postgres].") from exc
    return psycopg.connect
