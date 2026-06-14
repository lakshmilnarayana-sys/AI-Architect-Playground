from pathlib import Path

from typer.testing import CliRunner

from perfagent.cli import app
from perfagent.core.artifacts import read_json
import subprocess

from perfagent.executors import distributed
from perfagent.executors.distributed import build_distributed_coordinator_plan, build_distributed_plan


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


def test_build_distributed_coordinator_plan_has_worker_commands(tmp_path):
    plan = build_distributed_coordinator_plan(
        engine="k6",
        service_name="payments-api",
        workers=2,
        output_dir=tmp_path,
    )

    assert plan["mode"] == "distributed-coordinator"
    assert len(plan["worker_specs"]) == 2
    assert "PERFAGENT_WORKER_ID=worker-1" in plan["worker_specs"][0]["command"]
    assert "distributed merge" in plan["merge_command"]


def test_run_distributed_coordinator_executes_and_merges(tmp_path, monkeypatch):
    plan = build_distributed_coordinator_plan(
        engine="k6",
        service_name="payments-api",
        workers=1,
        output_dir=tmp_path,
    )

    def fake_run(command, text, capture_output, check):
        summary_path = Path(plan["worker_specs"][0]["summary_path"])
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            """{"metrics":{"http_reqs":{"count":10,"rate":5},"http_req_duration":{"percentiles":{"p(95)":100,"p(99)":150}},"http_req_failed":{"rate":0}}}"""
        )
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(distributed.subprocess, "run", fake_run)

    result = distributed.run_distributed_coordinator(plan, output_path=tmp_path / "run.json")

    assert result["success"] is True
    assert result["workers"][0]["exit_code"] == 0
    assert (tmp_path / "merged" / "raw" / "merged_summary.json").exists()
