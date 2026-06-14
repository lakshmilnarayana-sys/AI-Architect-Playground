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
