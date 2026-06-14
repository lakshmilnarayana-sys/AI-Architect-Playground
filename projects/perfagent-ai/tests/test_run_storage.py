import sqlite3
from datetime import UTC, datetime, timedelta

from perfagent.storage.run_store import RunStore, compare_to_latest_baseline


def test_run_store_records_run_and_applies_retention(tmp_path):
    db_path = tmp_path / "perfagent.db"
    store = RunStore(db_path)
    old_time = datetime.now(UTC) - timedelta(days=45)
    new_time = datetime.now(UTC)

    store.record_run(
        {
            "run_id": "old",
            "service_name": "payments-api",
            "release_decision": "PASS",
            "features": {"max_p95_latency_ms": 100},
            "report_html_path": "old.html",
            "created_at": old_time.isoformat(),
        }
    )
    store.record_run(
        {
            "run_id": "new",
            "service_name": "payments-api",
            "release_decision": "WARN",
            "features": {"max_p95_latency_ms": 200},
            "report_html_path": "new.html",
            "created_at": new_time.isoformat(),
        }
    )

    deleted = store.apply_retention(retention_days=30, now=new_time)

    assert deleted == 1
    assert [run["run_id"] for run in store.list_runs("payments-api")] == ["new"]


def test_compare_to_latest_baseline_detects_regression(tmp_path):
    store = RunStore(tmp_path / "perfagent.db")
    store.record_run(
        {
            "run_id": "baseline",
            "service_name": "payments-api",
            "release_decision": "PASS",
            "features": {"max_p95_latency_ms": 100, "stable_rps": 200, "max_error_rate_percent": 0.1},
            "report_html_path": "baseline.html",
            "created_at": "2026-06-13T10:00:00+00:00",
        }
    )
    current = {"max_p95_latency_ms": 130, "stable_rps": 180, "max_error_rate_percent": 0.4}

    result = compare_to_latest_baseline(
        store,
        "payments-api",
        current,
        max_p95_regression_percent=20,
        max_error_rate_delta_percent=0.2,
    )

    assert result["regression_detected"] is True
    assert "p95 latency regressed by 30.0%" in result["findings"]
    assert "error rate increased by 0.3 percentage points" in result["findings"]


def test_run_store_records_structured_artifacts_timeseries_and_findings(tmp_path):
    db_path = tmp_path / "perfagent.db"
    store = RunStore(db_path)

    store.record_run(
        {
            "run_id": "run-structured",
            "service_name": "payments-api",
            "features": {"max_p95_latency_ms": 150},
            "artifacts": [
                {"type": "report_html", "path": "reports/report.html", "content_type": "text/html", "size_bytes": 42}
            ],
            "aligned_timeseries": [
                {
                    "timestamp": "2026-06-14T10:00:00+00:00",
                    "phase": "steady",
                    "rps": 100,
                    "p95_latency_ms": 120,
                    "error_rate_percent": 0.1,
                    "virtual_users": 20,
                }
            ],
            "findings": [
                {
                    "type": "latency_regression",
                    "severity": "warn",
                    "evidence": "p95 exceeded target",
                    "recommendation": "inspect database waits",
                }
            ],
        }
    )

    with sqlite3.connect(db_path) as conn:
        artifact = conn.execute(
            "SELECT artifact_type, artifact_path, content_type, size_bytes FROM perf_artifacts"
        ).fetchone()
        sample = conn.execute(
            "SELECT phase, rps, p95_latency_ms, error_rate_percent, virtual_users FROM perf_timeseries"
        ).fetchone()
        finding = conn.execute(
            "SELECT finding_type, severity, evidence, recommendation FROM perf_findings"
        ).fetchone()

    assert artifact == ("report_html", "reports/report.html", "text/html", 42)
    assert sample == ("steady", 100.0, 120.0, 0.1, 20.0)
    assert finding == ("latency_regression", "warn", "p95 exceeded target", "inspect database waits")


def test_run_store_explicit_structured_helpers(tmp_path):
    store = RunStore(tmp_path / "perfagent.db")
    store.record_run({"run_id": "run-1", "service_name": "payments-api", "features": {}})

    assert store.record_artifacts("run-1", {"report": "reports/report.md"}) == 1
    assert store.record_timeseries("run-1", [{"timestamp": "2026-06-14T10:00:00+00:00", "rps": 10}]) == 1
    assert store.record_findings("run-1", ["missing dependency metrics"]) == 1
