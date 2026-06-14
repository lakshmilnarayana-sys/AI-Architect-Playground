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
