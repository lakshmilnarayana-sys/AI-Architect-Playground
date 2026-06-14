from __future__ import annotations

import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SUPPORTED_FORMATS = [
    "pprof",
    "jfr",
    "py-spy",
    "clinic",
    "collapsed-stacks",
    "speedscope",
    "v8-cpuprofile",
    "flamegraph",
]


def _classify_profile(profile_path: Path) -> str:
    name = profile_path.name.lower()
    suffixes = [suffix.lower() for suffix in profile_path.suffixes]

    if ".svg" in suffixes:
        return "flamegraph"
    if ".pprof" in suffixes or name.endswith(".pb.gz"):
        return "pprof"
    if ".jfr" in suffixes:
        return "jfr"
    if name.endswith(".speedscope.json") or "speedscope" in name:
        return "speedscope"
    if ".collapsed" in suffixes or name.endswith(".folded") or "collapsed" in name:
        return "collapsed-stacks"
    if ".cpuprofile" in suffixes:
        return "v8-cpuprofile"
    if "clinic" in name:
        return "clinic"
    if "py-spy" in name or "pyspy" in name:
        return "py-spy"
    return "unknown"


def _render_status(profile_type: str, exists: bool) -> str:
    if not exists:
        return "missing"
    if profile_type == "flamegraph":
        return "provided"
    return "not_rendered"


def _profile_warnings(profile_type: str, profile_path: Path, exists: bool) -> list[str]:
    if not exists:
        return [f"Profiling artifact not found: {profile_path}"]
    if profile_type == "flamegraph":
        return []
    if profile_type == "unknown":
        return ["Unrecognized profiling artifact type; copied without rendering."]
    return [f"Rendering is not implemented for {profile_type} profiles yet."]


def collect_profiling_artifacts(profile_paths: list[Path], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[str] = []
    warnings: list[str] = []
    profiles: list[dict[str, Any]] = []
    for profile_path in profile_paths:
        profile_type = _classify_profile(profile_path)
        if not profile_path.exists():
            profile_warnings = _profile_warnings(profile_type, profile_path, exists=False)
            warnings.extend(profile_warnings)
            profiles.append(
                {
                    "source_path": str(profile_path),
                    "artifact_path": None,
                    "type": profile_type,
                    "render_status": _render_status(profile_type, exists=False),
                    "warnings": profile_warnings,
                }
            )
            continue
        destination = output_dir / profile_path.name
        shutil.copyfile(profile_path, destination)
        artifacts.append(str(destination))
        profiles.append(
            {
                "source_path": str(profile_path),
                "artifact_path": str(destination),
                "type": profile_type,
                "render_status": _render_status(profile_type, exists=True),
                "warnings": _profile_warnings(profile_type, profile_path, exists=True),
            }
        )
    return {
        "enabled": bool(profile_paths),
        "artifacts": artifacts,
        "profiles": profiles,
        "warnings": warnings,
        "supported_formats": SUPPORTED_FORMATS,
    }


def build_profile_capture_plan(
    *,
    runtime: str,
    output_dir: Path,
    duration_seconds: int = 60,
    pid: str | None = None,
    profile_endpoint: str | None = None,
    container: str | None = None,
) -> dict[str, Any]:
    runtime_name = runtime.lower()
    output_dir = Path(output_dir)
    commands: list[dict[str, Any]] = []
    warnings: list[str] = []

    if runtime_name == "go":
        target = profile_endpoint or "http://localhost:6060/debug/pprof"
        cpu = output_dir / "cpu.pprof"
        commands.append(
            _command(
                "go",
                ["go", "tool", "pprof", "-proto", f"{target}/profile?seconds={duration_seconds}", "-output", str(cpu)],
                "Capture Go CPU profile from pprof endpoint.",
                phase="capture",
            )
        )
        commands.append(
            _command(
                "go",
                ["go", "tool", "pprof", "-svg", str(cpu)],
                "Render Go CPU profile as SVG flame graph.",
                phase="render",
            )
        )
    elif runtime_name in {"java", "jvm"}:
        target_pid = pid or "<pid>"
        jfr = output_dir / "perfagent.jfr"
        commands.append(
            _command(
                "jcmd",
                [
                    "jcmd",
                    target_pid,
                    "JFR.start",
                    "name=perfagent",
                    "settings=profile",
                    f"duration={duration_seconds}s",
                    f"filename={jfr}",
                ],
                "Capture Java Flight Recorder profile.",
                phase="capture",
            )
        )
        commands.append(_command("jcmd", ["jcmd", target_pid, "Thread.print"], "Capture Java thread dump.", phase="capture"))
    elif runtime_name == "python":
        target_pid = pid or "<pid>"
        commands.append(
            _command(
                "py-spy",
                [
                    "py-spy",
                    "record",
                    "--pid",
                    target_pid,
                    "--duration",
                    str(duration_seconds),
                    "--format",
                    "speedscope",
                    "--output",
                    str(output_dir / "py-spy.speedscope.json"),
                ],
                "Capture Python CPU profile in Speedscope format.",
                phase="capture",
            )
        )
    elif runtime_name in {"node", "nodejs", "javascript"}:
        if container:
            commands.append(
                _command(
                    "docker",
                    ["docker", "exec", container, "node", "--cpu-prof", "--heap-prof", "server.js"],
                    "Capture Node.js V8 CPU and heap profiles inside a container.",
                    phase="capture",
                )
            )
        commands.append(
            _command(
                "clinic",
                ["clinic", "flame", "--", "node", "server.js"],
                "Capture Node.js Clinic flame profile.",
                phase="capture",
            )
        )
    else:
        warnings.append(f"Unsupported runtime for automatic profiling plan: {runtime}")

    for command in commands:
        if not command["available"]:
            warnings.append(f"Required profiler binary not found: {command['binary']}")

    return {
        "runtime": runtime,
        "duration_seconds": duration_seconds,
        "output_dir": str(output_dir),
        "commands": commands,
        "warnings": warnings,
        "execute_supported": True,
        "execution_note": "PerfAgent can execute available capture commands when explicitly enabled.",
    }


def start_profile_capture_plan(plan: dict[str, Any], *, log_dir: Path) -> dict[str, Any]:
    """Start capture-phase profiler commands without using a shell."""
    log_dir.mkdir(parents=True, exist_ok=True)
    Path(plan.get("output_dir", log_dir)).mkdir(parents=True, exist_ok=True)
    started: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    warnings = list(plan.get("warnings", []))
    for index, command in enumerate(plan.get("commands", [])):
        if command.get("phase") != "capture":
            continue
        if not command.get("available"):
            skipped.append({"command": command.get("command"), "reason": "binary_missing"})
            continue
        stdout_path = log_dir / f"profile-capture-{index}.stdout.log"
        stderr_path = log_dir / f"profile-capture-{index}.stderr.log"
        stdout = stdout_path.open("w")
        stderr = stderr_path.open("w")
        process = subprocess.Popen(command["argv"], stdout=stdout, stderr=stderr, text=True)
        started.append(
            {
                "index": index,
                "pid": process.pid,
                "argv": command["argv"],
                "command": command["command"],
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
                "_process": process,
                "_stdout": stdout,
                "_stderr": stderr,
                "started_at": datetime.now(UTC).isoformat(),
            }
        )
    return {"enabled": bool(started or skipped), "started": started, "skipped": skipped, "warnings": warnings}


def finish_profile_capture_plan(
    plan: dict[str, Any],
    capture: dict[str, Any],
    *,
    log_dir: Path,
    timeout_seconds: int = 15,
) -> dict[str, Any]:
    log_dir.mkdir(parents=True, exist_ok=True)
    completed: list[dict[str, Any]] = []
    warnings = list(capture.get("warnings", []))
    for item in capture.get("started", []):
        process = item.get("_process")
        started_at = time.perf_counter()
        exit_code = None
        if process is not None:
            try:
                exit_code = process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                process.terminate()
                warnings.append(f"Profiler command timed out and was terminated: {item.get('command')}")
                try:
                    exit_code = process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    exit_code = process.wait(timeout=5)
        for handle_name in ("_stdout", "_stderr"):
            handle = item.get(handle_name)
            if handle:
                handle.close()
        completed.append(
            {
                "command": item.get("command"),
                "pid": item.get("pid"),
                "exit_code": exit_code,
                "duration_seconds": round(time.perf_counter() - started_at, 4),
                "stdout_path": item.get("stdout_path"),
                "stderr_path": item.get("stderr_path"),
                "started_at": item.get("started_at"),
                "ended_at": datetime.now(UTC).isoformat(),
            }
        )

    render_results = _run_render_commands(plan, log_dir=log_dir)
    warnings.extend(render_results["warnings"])
    return {
        "enabled": capture.get("enabled", False),
        "plan": _public_plan(plan),
        "started_count": len(capture.get("started", [])),
        "skipped": capture.get("skipped", []),
        "completed": completed,
        "rendered": render_results["completed"],
        "warnings": warnings,
    }


def execute_profile_capture_plan(plan: dict[str, Any], *, log_dir: Path, timeout_seconds: int | None = None) -> dict[str, Any]:
    capture = start_profile_capture_plan(plan, log_dir=log_dir)
    wait_timeout = timeout_seconds if timeout_seconds is not None else int(plan.get("duration_seconds", 60)) + 30
    return finish_profile_capture_plan(plan, capture, log_dir=log_dir, timeout_seconds=wait_timeout)


def _run_render_commands(plan: dict[str, Any], *, log_dir: Path) -> dict[str, Any]:
    completed: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, command in enumerate(plan.get("commands", [])):
        if command.get("phase") != "render":
            continue
        if not command.get("available"):
            warnings.append(f"Render command skipped because binary is missing: {command.get('binary')}")
            continue
        stdout_path = log_dir / f"profile-render-{index}.stdout.log"
        stderr_path = log_dir / f"profile-render-{index}.stderr.log"
        result = subprocess.run(command["argv"], text=True, capture_output=True, check=False)
        stdout_path.write_text(result.stdout)
        stderr_path.write_text(result.stderr)
        completed.append(
            {
                "command": command["command"],
                "exit_code": result.returncode,
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
            }
        )
    return {"completed": completed, "warnings": warnings}


def _public_plan(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in plan.items()
        if key != "commands"
    } | {"commands": [{key: value for key, value in command.items() if not key.startswith("_")} for command in plan.get("commands", [])]}


def _command(binary: str, argv: list[str], description: str, *, phase: str) -> dict[str, Any]:
    return {
        "binary": binary,
        "available": shutil.which(binary) is not None,
        "argv": argv,
        "command": " ".join(argv),
        "description": description,
        "phase": phase,
    }
