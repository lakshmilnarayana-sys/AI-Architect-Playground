from pathlib import Path

from typer.testing import CliRunner

from perfagent.cli import app
from perfagent.collectors.external_results import load_jmeter_results, load_locust_results


runner = CliRunner()


def test_load_locust_results_from_stats_csv(tmp_path):
    stats = tmp_path / "locust_stats.csv"
    stats.write_text(
        "Type,Name,Request Count,Failure Count,Requests/s,95%,99%\n"
        "GET,/health,10,0,5,20,30\n"
        ",Aggregated,100,2,25.5,120,180\n"
    )

    summary, aligned = load_locust_results(stats)

    assert summary["metrics"]["http_reqs"]["count"] == 100
    assert summary["metrics"]["http_reqs"]["rate"] == 25.5
    assert summary["metrics"]["http_req_duration"]["percentiles"]["p(95)"] == 120
    assert aligned[0]["error_rate_percent"] == 2.0


def test_load_locust_results_prefers_history_buckets(tmp_path):
    stats = tmp_path / "locust_stats.csv"
    stats.write_text(
        "Type,Name,Request Count,Failure Count,Requests/s,95%,99%\n"
        ",Aggregated,100,2,25.5,120,180\n"
    )
    history = tmp_path / "locust_stats_history.csv"
    history.write_text(
        "Timestamp,User Count,Type,Name,Requests/s,Failures/s,95%,99%\n"
        "1781344800,10,,Aggregated,25,0.1,120,180\n"
        "1781344810,20,,Aggregated,50,0.2,220,300\n"
    )

    _, aligned = load_locust_results(stats)

    assert len(aligned) == 2
    assert aligned[0]["timestamp"] == "2026-06-13T10:00:00Z"
    assert aligned[1]["rps"] == 50
    assert aligned[1]["virtual_users"] == 20


def test_load_jmeter_results_from_jtl_csv(tmp_path):
    jtl = tmp_path / "jmeter_results.jtl"
    jtl.write_text(
        "timeStamp,elapsed,label,responseCode,success\n"
        "1781344800000,100,GET /health,200,true\n"
        "1781344801000,200,GET /health,500,false\n"
        "1781344802000,300,GET /health,200,true\n"
    )

    summary, aligned = load_jmeter_results(jtl)

    assert summary["metrics"]["http_reqs"]["count"] == 3
    assert summary["metrics"]["http_req_failed"]["fails"] == 1
    assert aligned[0]["p95_latency_ms"] == 300
    assert aligned[0]["error_rate_percent"] == 33.3333


def test_load_jmeter_results_buckets_samples_by_10_seconds(tmp_path):
    jtl = tmp_path / "jmeter_results.jtl"
    jtl.write_text(
        "timeStamp,elapsed,label,responseCode,success\n"
        "1781344800000,100,GET /health,200,true\n"
        "1781344801000,200,GET /health,200,true\n"
        "1781344811000,300,GET /health,500,false\n"
    )

    _, aligned = load_jmeter_results(jtl)

    assert len(aligned) == 2
    assert aligned[0]["timestamp"] == "2026-06-13T10:00:00Z"
    assert aligned[0]["rps"] == 0.2
    assert aligned[1]["error_rate_percent"] == 100.0


def test_import_results_command_generates_perfagent_report(tmp_path):
    run_dir = tmp_path / "run"
    result_path = tmp_path / "locust_stats.csv"
    result_path.write_text(
        "Type,Name,Request Count,Failure Count,Requests/s,95%,99%\n"
        ",Aggregated,100,0,25,120,180\n"
    )

    result = runner.invoke(
        app,
        [
            "import-results",
            "--run-dir",
            str(run_dir),
            "--tool",
            "locust",
            "--result",
            str(result_path),
            "--service-name",
            "payments-api",
            "--runtime",
            "python",
            "--target-url",
            "http://localhost:8080",
            "--slo-p95-ms",
            "500",
            "--slo-error-rate",
            "1",
        ],
    )

    assert result.exit_code == 0, result.output
    assert (run_dir / "reports" / "report.html").exists()
    assert (run_dir / "reports" / "report.md").exists()
    assert (run_dir / "processed" / "features.json").exists()
