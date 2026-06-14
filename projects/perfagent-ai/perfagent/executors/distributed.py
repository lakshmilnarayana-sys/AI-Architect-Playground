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
