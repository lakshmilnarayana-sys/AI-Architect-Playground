from __future__ import annotations

import shutil
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
            )
        )
        commands.append(
            _command("go", ["go", "tool", "pprof", "-svg", str(cpu)], "Render Go CPU profile as SVG flame graph.")
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
            )
        )
        commands.append(_command("jcmd", ["jcmd", target_pid, "Thread.print"], "Capture Java thread dump."))
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
            )
        )
    elif runtime_name in {"node", "nodejs", "javascript"}:
        if container:
            commands.append(
                _command(
                    "docker",
                    ["docker", "exec", container, "node", "--cpu-prof", "--heap-prof", "server.js"],
                    "Capture Node.js V8 CPU and heap profiles inside a container.",
                )
            )
        commands.append(
            _command(
                "clinic",
                ["clinic", "flame", "--", "node", "server.js"],
                "Capture Node.js Clinic flame profile.",
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
        "execute_supported": False,
        "execution_note": "PerfAgent currently plans profiler commands; automatic execution is intentionally opt-in future work.",
    }


def _command(binary: str, argv: list[str], description: str) -> dict[str, Any]:
    return {
        "binary": binary,
        "available": shutil.which(binary) is not None,
        "argv": argv,
        "command": " ".join(argv),
        "description": description,
    }
