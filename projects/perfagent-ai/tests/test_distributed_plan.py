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


def test_distributed_merge_command_writes_merged_artifacts(tmp_path):
    worker = tmp_path / "worker.json"
    output_dir = tmp_path / "merged"
    worker.write_text(
        """{"metrics":{"http_reqs":{"count":10,"rate":5},"http_req_duration":{"percentiles":{"p(95)":100,"p(99)":150}},"http_req_failed":{"rate":0}}}"""
    )

    result = runner.invoke(
        app,
        ["distributed", "merge", "--worker-summary", str(worker), "--output-dir", str(output_dir)],
    )

    assert result.exit_code == 0, result.output
    assert (output_dir / "raw" / "merged_summary.json").exists()
    assert (output_dir / "processed" / "aligned_timeseries.csv").exists()
