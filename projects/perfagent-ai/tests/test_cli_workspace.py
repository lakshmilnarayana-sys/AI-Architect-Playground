from pathlib import Path

from typer.testing import CliRunner

from perfagent.analyzers import features as feature_module
from perfagent.cli import app


runner = CliRunner()


def test_evaluate_skip_run_creates_mvp_artifacts(tmp_path):
    output = tmp_path / "reports" / "payments-api"
    result = runner.invoke(
        app,
        [
            "evaluate",
            "--service-name",
            "payments-api",
            "--openapi",
            "examples/sample-openapi.yaml",
            "--target-url",
            "http://localhost:8080",
            "--runtime",
            "go",
            "--slo-p95-ms",
            "500",
            "--slo-error-rate",
            "1",
            "--duration",
            "1m",
            "--output",
            str(output),
            "--skip-run",
        ],
    )

    assert result.exit_code == 0, result.output
    assert (output / "state" / "evaluation_state.json").exists()
    assert (output / "processed" / "contract_analysis.json").exists()
    assert (output / "generated" / "test_data.json").exists()
    assert (output / "generated" / "perf_test.js").exists()
    assert (output / "generated" / "locustfile.py").exists()
    assert (output / "generated" / "jmeter_test_plan.jmx").exists()
    assert (output / "processed" / "features.json").exists()
    assert (output / "processed" / "bottleneck_analysis.json").exists()
    assert (output / "reports" / "report.md").exists()
    assert (output / "reports" / "report.html").exists()


def test_generate_command_creates_k6_script_without_execution(tmp_path):
    output = tmp_path / "generated" / "payments-api"
    result = runner.invoke(
        app,
        [
            "generate",
            "--service-name",
            "payments-api",
            "--openapi",
            "examples/sample-openapi.yaml",
            "--target-url",
            "http://localhost:8080",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert (output / "contract_analysis.json").exists()
    assert (output / "test_data.json").exists()
    assert (output / "perf_test.js").exists()
    assert (output / "locustfile.py").exists()
    assert (output / "jmeter_test_plan.jmx").exists()


def test_evaluate_fail_on_exits_non_zero_for_matching_decision(tmp_path, monkeypatch):
    monkeypatch.setattr(
        feature_module,
        "release_decision",
        lambda features, aligned_timeseries: "BLOCK",
    )
    output = tmp_path / "reports" / "payments-api"
    result = runner.invoke(
        app,
        [
            "evaluate",
            "--service-name",
            "payments-api",
            "--openapi",
            "examples/sample-openapi.yaml",
            "--target-url",
            "http://localhost:8080",
            "--runtime",
            "go",
            "--slo-p95-ms",
            "500",
            "--slo-error-rate",
            "1",
            "--output",
            str(output),
            "--skip-run",
            "--fail-on",
            "BLOCK,UNKNOWN",
        ],
    )

    assert result.exit_code == 2
    assert "Performance gate failed: BLOCK" in result.output
