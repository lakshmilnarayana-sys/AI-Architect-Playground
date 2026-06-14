from typer.testing import CliRunner

from perfagent.cli import app
from perfagent.core.artifacts import write_json
from perfagent.storage.run_store import RunStore


runner = CliRunner()


def test_regression_compare_command_detects_regression(tmp_path):
    db_path = tmp_path / "perfagent.db"
    store = RunStore(db_path)
    store.record_run(
        {
            "run_id": "baseline",
            "service_name": "payments-api",
            "release_decision": "PASS",
            "features": {"max_p95_latency_ms": 100, "max_error_rate_percent": 0.1},
            "report_html_path": "baseline.html",
            "created_at": "2026-06-13T10:00:00+00:00",
        }
    )
    run_dir = tmp_path / "run"
    write_json(
        run_dir / "reports" / "summary.json",
        {
            "run_id": "current",
            "service_name": "payments-api",
            "features": {"max_p95_latency_ms": 150, "max_error_rate_percent": 0.8},
        },
    )
    output_json = run_dir / "processed" / "regression.json"

    result = runner.invoke(
        app,
        [
            "regression",
            "compare",
            "--run-dir",
            str(run_dir),
            "--db-path",
            str(db_path),
            "--max-p95-regression-percent",
            "20",
            "--max-error-rate-delta-percent",
            "0.5",
            "--output-json",
            str(output_json),
            "--fail-on-regression",
        ],
    )

    assert result.exit_code == 2
    assert "Regression detected: True" in result.output
    assert output_json.exists()


def test_regression_similar_command_uses_sql_history_without_pgvector(tmp_path):
    db_path = tmp_path / "perfagent.db"
    store = RunStore(db_path)
    store.record_run(
        {
            "run_id": "warn-run",
            "service_name": "payments-api",
            "release_decision": "WARN",
            "features": {"max_p95_latency_ms": 900, "max_error_rate_percent": 3.2, "breaking_point_rps": 500},
            "report_html_path": "warn.html",
        }
    )
    output_json = tmp_path / "similar.json"

    result = runner.invoke(
        app,
        [
            "regression",
            "similar",
            "--query",
            "p95 latency regression during stress",
            "--db-path",
            str(db_path),
            "--service-name",
            "payments-api",
            "--output-json",
            str(output_json),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "warn-run" in result.output
    assert output_json.exists()
