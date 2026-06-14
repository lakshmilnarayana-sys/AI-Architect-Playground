from perfagent.storage.postgres_store import PostgresRunStore


class FakeCursor:
    def __init__(self):
        self.statements = []
        self.rowcount = 0
        self.description = [("run_id",), ("service_name",)]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.statements.append((query, params))

    def fetchall(self):
        return [("run-1", "payments-api")]


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_instance = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self.cursor_instance


def test_postgres_store_records_run_and_lists_rows():
    cursors = []

    def fake_connect(dsn):
        cursor = FakeCursor()
        cursors.append(cursor)
        return FakeConnection(cursor)

    store = PostgresRunStore("postgresql://example", connect=fake_connect)
    store.record_run(
        {
            "run_id": "run-1",
            "service_name": "payments-api",
            "release_decision": "PASS",
            "features": {"stable_rps": 10, "max_p95_latency_ms": 100, "max_error_rate_percent": 0.1},
            "report_html_path": "report.html",
            "artifacts": [{"type": "report_html", "path": "report.html", "content_type": "text/html"}],
            "aligned_timeseries": [
                {"timestamp": "2026-06-14T10:00:00+00:00", "phase": "steady", "rps": 10, "p95_latency_ms": 100}
            ],
            "findings": [{"type": "latency", "severity": "warn", "evidence": "p95 increased"}],
        }
    )
    rows = store.list_runs("payments-api")

    statements = "\n".join(statement for cursor in cursors for statement, _ in cursor.statements)
    assert "CREATE TABLE IF NOT EXISTS perf_runs" in statements
    assert "CREATE TABLE IF NOT EXISTS perf_features" in statements
    assert "CREATE TABLE IF NOT EXISTS perf_artifacts" in statements
    assert "CREATE TABLE IF NOT EXISTS perf_timeseries" in statements
    assert "CREATE TABLE IF NOT EXISTS perf_dependencies" in statements
    assert "content_type TEXT" in statements
    assert "virtual_users DOUBLE PRECISION" in statements
    assert "source TEXT" in statements
    assert "ON CONFLICT (run_id) DO UPDATE" in statements
    assert "INSERT INTO perf_artifacts" in statements
    assert "INSERT INTO perf_timeseries" in statements
    assert "INSERT INTO perf_findings" in statements
    assert rows == [{"run_id": "run-1", "service_name": "payments-api"}]


def test_postgres_store_explicit_structured_helpers_use_fake_connection():
    cursors = []

    def fake_connect(dsn):
        cursor = FakeCursor()
        cursors.append(cursor)
        return FakeConnection(cursor)

    store = PostgresRunStore("postgresql://example", connect=fake_connect)

    artifact_count = store.record_artifacts("run-1", {"report": "report.md"})
    sample_count = store.record_timeseries("run-1", [{"timestamp": "2026-06-14T10:00:00+00:00", "rps": 25}])
    finding_count = store.record_findings("run-1", ["no baseline run available"])

    statements = "\n".join(statement for cursor in cursors for statement, _ in cursor.statements)
    assert artifact_count == 1
    assert sample_count == 1
    assert finding_count == 1
    assert "INSERT INTO perf_artifacts" in statements
    assert "INSERT INTO perf_timeseries" in statements
    assert "INSERT INTO perf_findings" in statements
