from __future__ import annotations

import subprocess
import shlex
from pathlib import Path
from typing import Any

from perfagent.collectors.distributed_results import write_merged_worker_results
from perfagent.core.artifacts import write_json


def build_distributed_plan(
    *,
    engine: str,
    service_name: str,
    workers: int,
    output_dir: Path,
    compose_service: str = "perfagent",
) -> dict[str, Any]:
    workers = max(1, int(workers))
    output = str(output_dir)
    commands = [
        f"docker compose build {compose_service}",
        (
            f"docker compose run --rm --scale {compose_service}={workers} {compose_service} evaluate "
            f"--config ./examples/sample-config.yaml --engine {engine} --output {output}"
        ),
    ]
    return {
        "mode": "distributed-container",
        "engine": engine,
        "service_name": service_name,
        "workers": workers,
        "compose_service": compose_service,
        "output_dir": output,
        "commands": commands,
        "warnings": [
            "MVP distributed mode is a plan generator; coordinated result merge is still required for multi-worker execution."
        ],
    }


def build_distributed_coordinator_plan(
    *,
    engine: str,
    service_name: str,
    workers: int,
    output_dir: Path,
    base_config: str = "./examples/sample-config.yaml",
    compose_service: str = "perfagent",
    backend: str = "local",
    compose_file: str = "docker-compose.yml",
    project_name: str | None = None,
) -> dict[str, Any]:
    workers = max(1, int(workers))
    worker_specs = []
    output_dir = Path(output_dir)
    project_name = project_name or f"perfagent-{service_name}".replace("_", "-")
    compose_prefix = f"docker compose -f {compose_file} -p {project_name}" if backend == "docker-compose" else "docker compose"
    for index in range(workers):
        worker_id = f"worker-{index + 1}"
        worker_output = output_dir / worker_id
        summary_path = worker_output / "raw" / "k6_summary.json"
        environment = {
            "PERFAGENT_WORKER_ID": worker_id,
            "PERFAGENT_SERVICE_NAME": service_name,
            "PERFAGENT_ENGINE": engine,
        }
        env_args = " ".join(f"-e {key}={value}" for key, value in environment.items())
        worker_specs.append(
            {
                "worker_id": worker_id,
                "output_dir": str(worker_output),
                "summary_path": str(summary_path),
                "environment": environment,
                "command": (
                    f"{compose_prefix} run --rm {env_args} {compose_service} evaluate "
                    f"--config {base_config} --service-name {service_name} --engine {engine} "
                    f"--output {worker_output}"
                ),
            }
        )
    merge_command = (
        "perfagent distributed merge "
        + " ".join(f"--worker-summary {worker['summary_path']}" for worker in worker_specs)
        + f" --output-dir {output_dir / 'merged'}"
    )
    return {
        "mode": "distributed-coordinator",
        "backend": backend,
        "engine": engine,
        "service_name": service_name,
        "workers": workers,
        "compose_service": compose_service,
        "compose_file": compose_file,
        "project_name": project_name,
        "output_dir": str(output_dir),
        "lifecycle": {
            "setup": [f"{compose_prefix} build {compose_service}"] if backend == "docker-compose" else [],
            "teardown": [f"{compose_prefix} down --remove-orphans"] if backend == "docker-compose" else [],
        },
        "worker_specs": worker_specs,
        "merge_command": merge_command,
        "warnings": [
            "Coordinator plan is deterministic; use --execute to run worker lifecycle commands.",
            "Use distributed merge after worker summaries are available.",
        ],
    }


def run_distributed_coordinator(plan: dict[str, Any], *, output_path: Path | None = None) -> dict[str, Any]:
    worker_results: list[dict[str, Any]] = []
    lifecycle_results: list[dict[str, Any]] = []
    for command in plan.get("lifecycle", {}).get("setup", []):
        setup_result = subprocess.run(shlex.split(command), text=True, capture_output=True, check=False)
        lifecycle_results.append(
            {
                "phase": "setup",
                "command": command,
                "exit_code": setup_result.returncode,
                "stdout": setup_result.stdout[-4000:],
                "stderr": setup_result.stderr[-4000:],
            }
        )
        if setup_result.returncode != 0:
            result = {
                "mode": "distributed-coordinator-execution",
                "plan": plan,
                "lifecycle": lifecycle_results,
                "workers": [],
                "merged": None,
                "success": False,
                "warnings": ["Distributed setup failed; workers were not started."],
            }
            if output_path:
                write_json(output_path, result)
            return result
    for worker in plan.get("worker_specs", []):
        result = subprocess.run(shlex.split(worker["command"]), text=True, capture_output=True, check=False)
        worker_results.append(
            {
                "worker_id": worker.get("worker_id"),
                "command": worker.get("command"),
                "exit_code": result.returncode,
                "summary_path": worker.get("summary_path"),
                "stdout": result.stdout[-4000:],
                "stderr": result.stderr[-4000:],
            }
        )
    summary_paths = [Path(worker["summary_path"]) for worker in plan.get("worker_specs", []) if Path(worker["summary_path"]).exists()]
    merged: dict[str, Any] | None = None
    if summary_paths:
        merged = write_merged_worker_results(
            summary_paths,
            summary_path=Path(plan["output_dir"]) / "merged" / "raw" / "merged_summary.json",
            aligned_path=Path(plan["output_dir"]) / "merged" / "processed" / "aligned_timeseries.csv",
        )
    for command in plan.get("lifecycle", {}).get("teardown", []):
        teardown_result = subprocess.run(shlex.split(command), text=True, capture_output=True, check=False)
        lifecycle_results.append(
            {
                "phase": "teardown",
                "command": command,
                "exit_code": teardown_result.returncode,
                "stdout": teardown_result.stdout[-4000:],
                "stderr": teardown_result.stderr[-4000:],
            }
        )
    result = {
        "mode": "distributed-coordinator-execution",
        "plan": plan,
        "lifecycle": lifecycle_results,
        "workers": worker_results,
        "merged": merged,
        "success": all(item["exit_code"] == 0 for item in lifecycle_results) and all(worker["exit_code"] == 0 for worker in worker_results) and bool(merged),
        "warnings": [] if merged else ["No worker summaries were available to merge."],
    }
    if output_path:
        write_json(output_path, result)
    return result
