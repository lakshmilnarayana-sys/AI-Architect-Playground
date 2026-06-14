from pathlib import Path

from typer.testing import CliRunner

from perfagent.cli import app
from perfagent.core.artifacts import read_json
from perfagent.executors.distributed import build_distributed_plan


runner = CliRunner()


def test_build_distributed_plan_outputs_compose_commands(tmp_path):
    plan = build_distributed_plan(engine="k6", service_name="payments-api", workers=3, output_dir=tmp_path)

    assert plan["workers"] == 3
    assert "docker compose build perfagent" in plan["commands"][0]
    assert "--scale perfagent=3" in plan["commands"][1]


def test_distributed_plan_command_writes_json(tmp_path):
    output = tmp_path / "plan.json"
    result = runner.invoke(
        app,
        ["distributed", "plan", "--service-name", "payments-api", "--engine", "k6", "--workers", "2", "--output", str(output)],
    )

    assert result.exit_code == 0, result.output
    assert read_json(output)["workers"] == 2
