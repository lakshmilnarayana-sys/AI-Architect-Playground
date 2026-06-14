from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

K6_DOCKER_IMAGE = "grafana/k6:latest"


def run_k6(script_path: Path, summary_path: Path, timeseries_path: Path, log_path: Path) -> dict[str, Any]:
    start = datetime.now(UTC).isoformat()
    command = build_k6_command(
        script_path,
        summary_path,
        timeseries_path,
        k6_path=shutil.which("k6"),
        docker_path=shutil.which("docker"),
    )
    if command is None:
        result = {
            "exit_code": 127,
            "started_at": start,
            "ended_at": datetime.now(UTC).isoformat(),
            "summary_path": str(summary_path),
            "timeseries_path": str(timeseries_path),
            "stdout": "",
            "stderr": "k6 executable not found and Docker fallback is unavailable",
            "skipped": True,
            "runtime": "missing",
        }
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(result["stderr"] + "\n")
        return result

    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(completed.stdout + "\n" + completed.stderr)
    return {
        "exit_code": completed.returncode,
        "started_at": start,
        "ended_at": datetime.now(UTC).isoformat(),
        "summary_path": str(summary_path),
        "timeseries_path": str(timeseries_path),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "skipped": False,
        "runtime": "native" if Path(command[0]).name == "k6" else "docker",
        "command": command,
    }


def read_k6_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"metrics": {}}
    return json.loads(path.read_text())


def build_k6_command(
    script_path: Path,
    summary_path: Path,
    timeseries_path: Path,
    *,
    k6_path: str | None,
    docker_path: str | None,
) -> list[str] | None:
    if k6_path:
        return [
            k6_path,
            "run",
            "--summary-export",
            str(summary_path),
            "--out",
            f"json={timeseries_path}",
            str(script_path),
        ]
    if not docker_path:
        return None

    mount_root = _common_workspace_root(script_path, summary_path, timeseries_path)
    container_script = _container_path(script_path, mount_root)
    container_summary = _container_path(summary_path, mount_root)
    container_timeseries = _container_path(timeseries_path, mount_root)
    return [
        docker_path,
        "run",
        "--rm",
        "-v",
        f"{mount_root}:/work",
        "-w",
        "/work",
        K6_DOCKER_IMAGE,
        "run",
        "--summary-export",
        container_summary,
        "--out",
        f"json={container_timeseries}",
        container_script,
    ]


def _common_workspace_root(script_path: Path, summary_path: Path, timeseries_path: Path) -> Path:
    common = os.path.commonpath([script_path.resolve(), summary_path.resolve(), timeseries_path.resolve()])
    path = Path(common)
    return path if path.is_dir() else path.parent


def _container_path(path: Path, mount_root: Path) -> str:
    return "/work/" + path.resolve().relative_to(mount_root).as_posix()
