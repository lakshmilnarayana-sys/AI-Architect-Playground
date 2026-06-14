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
        }
    )
    rows = store.list_runs("payments-api")

    statements = "\n".join(statement for cursor in cursors for statement, _ in cursor.statements)
    assert "CREATE TABLE IF NOT EXISTS perf_runs" in statements
    assert "ON CONFLICT (run_id) DO UPDATE" in statements
    assert rows == [{"run_id": "run-1", "service_name": "payments-api"}]
