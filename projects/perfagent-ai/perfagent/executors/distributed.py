from __future__ import annotations

from pathlib import Path
from typing import Any


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
) -> dict[str, Any]:
    workers = max(1, int(workers))
    worker_specs = []
    output_dir = Path(output_dir)
    for index in range(workers):
        worker_id = f"worker-{index + 1}"
        worker_output = output_dir / worker_id
        summary_path = worker_output / "raw" / "k6_summary.json"
        worker_specs.append(
            {
                "worker_id": worker_id,
                "output_dir": str(worker_output),
                "summary_path": str(summary_path),
                "command": (
                    f"docker compose run --rm -e PERFAGENT_WORKER_ID={worker_id} {compose_service} evaluate "
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
        "engine": engine,
        "service_name": service_name,
        "workers": workers,
        "compose_service": compose_service,
        "output_dir": str(output_dir),
        "worker_specs": worker_specs,
        "merge_command": merge_command,
        "warnings": [
            "Coordinator plan is deterministic; automatic worker lifecycle execution is not enabled by default.",
            "Use distributed merge after worker summaries are available.",
        ],
    }
