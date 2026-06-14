from typer.testing import CliRunner

from perfagent.cli import app
from perfagent.core.artifacts import read_json


runner = CliRunner()


def test_profile_plan_command_writes_json(tmp_path):
    output = tmp_path / "profile-plan.json"

    result = runner.invoke(
        app,
        ["profile", "plan", "--runtime", "python", "--output-dir", str(tmp_path), "--output-json", str(output)],
    )

    assert result.exit_code == 0, result.output
    assert read_json(output)["runtime"] == "python"


def test_observability_query_pack_command_writes_json(tmp_path):
    output = tmp_path / "query-pack.json"

    result = runner.invoke(
        app,
        [
            "observability",
            "query-pack",
            "--provider",
            "datadog",
            "--service-name",
            "payments-api",
            "--output-json",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert read_json(output)["provider"] == "datadog"


def test_distributed_coordinate_command_writes_plan(tmp_path):
    output = tmp_path / "coordinator.json"

    result = runner.invoke(
        app,
        ["distributed", "coordinate", "--service-name", "payments-api", "--workers", "2", "--output", str(output)],
    )

    assert result.exit_code == 0, result.output
    assert read_json(output)["mode"] == "distributed-coordinator"


def test_capacity_search_command_writes_summary(tmp_path, monkeypatch):
    output = tmp_path / "capacity"
    openapi = tmp_path / "openapi.yaml"
    openapi.write_text("openapi: 3.0.0\ninfo: {title: t, version: v}\npaths: {}\n")

    def fake_search(**kwargs):
        return {"estimated_capacity_rps": 100, "breaking_point_rps": 200, "probes": []}

    monkeypatch.setattr("perfagent.cli.run_capacity_search", fake_search)

    result = runner.invoke(
        app,
        [
            "capacity",
            "search",
            "--service-name",
            "payments-api",
            "--openapi",
            str(openapi),
            "--target-url",
            "http://localhost:8080",
            "--runtime",
            "python",
            "--slo-p95-ms",
            "500",
            "--slo-error-rate",
            "1",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Estimated capacity RPS: 100" in result.output


def test_profile_run_command_writes_json(tmp_path, monkeypatch):
    output = tmp_path / "profile-result.json"

    monkeypatch.setattr(
        "perfagent.cli.execute_profile_capture_plan",
        lambda plan, log_dir, timeout_seconds: {"started_count": 0, "warnings": [], "completed": [], "rendered": []},
    )

    result = runner.invoke(
        app,
        ["profile", "run", "--runtime", "python", "--output-json", str(output), "--output-dir", str(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    assert read_json(output)["started_count"] == 0
