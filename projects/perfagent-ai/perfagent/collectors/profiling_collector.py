from __future__ import annotations

import json
import re
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
                "summary": summarize_profile_artifact(destination, profile_type),
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
    mode: str = "runtime",
) -> dict[str, Any]:
    runtime_name = runtime.lower()
    output_dir = Path(output_dir)
    commands: list[dict[str, Any]] = []
    warnings: list[str] = []

    if mode.lower() in {"ebpf", "system", "auto"}:
        commands.extend(_ebpf_commands(output_dir=output_dir, duration_seconds=duration_seconds, pid=pid, container=container))
        if mode.lower() == "ebpf":
            runtime_name = "ebpf"

    if commands and mode.lower() in {"ebpf", "system"}:
        pass
    elif runtime_name == "go":
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
    elif not commands:
        warnings.append(f"Unsupported runtime for automatic profiling plan: {runtime}")

    for command in commands:
        if not command["available"]:
            warnings.append(f"Required profiler binary not found: {command['binary']}")

    return {
        "runtime": runtime,
        "mode": mode,
        "duration_seconds": duration_seconds,
        "output_dir": str(output_dir),
        "commands": commands,
        "warnings": warnings,
        "execute_supported": True,
        "execution_note": "PerfAgent can execute available capture commands when explicitly enabled.",
    }


def _ebpf_commands(*, output_dir: Path, duration_seconds: int, pid: str | None, container: str | None) -> list[dict[str, Any]]:
    target_pid = pid or "<pid>"
    commands = [
        _command(
            "perf",
            ["perf", "record", "-F", "99", "-g", "-p", target_pid, "--", "sleep", str(duration_seconds)],
            "Capture language-independent CPU stacks with Linux perf/eBPF without application instrumentation.",
            phase="capture",
        ),
        _command(
            "perf",
            ["perf", "script", "-i", str(output_dir / "perf.data")],
            "Convert perf.data into folded stack input for flamegraph tooling.",
            phase="render",
        ),
        _command(
            "bpftrace",
            ["bpftrace", "-e", f"profile:hz:99 /pid == {target_pid}/ {{ @[ustack] = count(); }}", "-d"],
            "Validate bpftrace user-stack profile program for the target PID.",
            phase="capture",
        ),
        _command(
            "pyroscope",
            ["pyroscope", "ebpf", "--pid", target_pid, "--duration", f"{duration_seconds}s", "--output", str(output_dir / "pyroscope.pb.gz")],
            "Capture eBPF profile with Pyroscope without code instrumentation.",
            phase="capture",
        ),
        _command(
            "parca-agent",
            ["parca-agent", "--remote-store-address", "127.0.0.1:7070", "--node", container or "local"],
            "Run Parca Agent eBPF profiler for language-independent continuous profiling.",
            phase="capture",
        ),
    ]
    return commands


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
    captured_artifacts = _captured_artifacts(Path(plan.get("output_dir", log_dir)))
    return {
        "enabled": capture.get("enabled", False),
        "plan": _public_plan(plan),
        "started_count": len(capture.get("started", [])),
        "skipped": capture.get("skipped", []),
        "completed": completed,
        "rendered": render_results["completed"],
        "artifacts": captured_artifacts,
        "warnings": warnings,
    }


def summarize_profile_artifact(profile_path: Path, profile_type: str | None = None) -> dict[str, Any]:
    profile_type = profile_type or _classify_profile(profile_path)
    if not profile_path.exists():
        return {"available": False, "top_functions": [], "warnings": ["profile artifact missing"]}
    if profile_type == "collapsed-stacks":
        return _summarize_collapsed_stacks(profile_path)
    if profile_type == "speedscope":
        return _summarize_speedscope(profile_path)
    if profile_type in {"pprof", "py-spy", "clinic", "v8-cpuprofile", "jfr"}:
        return _summarize_text_profile(profile_path)
    if profile_type == "flamegraph":
        return {"available": True, "type": "flamegraph", "top_functions": [], "warnings": []}
    return {"available": True, "type": profile_type, "top_functions": [], "warnings": ["profile summary parser unavailable"]}


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


def _captured_artifacts(output_dir: Path) -> list[dict[str, Any]]:
    if not output_dir.exists():
        return []
    artifacts: list[dict[str, Any]] = []
    for path in sorted(item for item in output_dir.iterdir() if item.is_file()):
        profile_type = _classify_profile(path)
        artifacts.append(
            {
                "artifact_path": str(path),
                "type": profile_type,
                "render_status": _render_status(profile_type, exists=True),
                "summary": summarize_profile_artifact(path, profile_type),
            }
        )
    return artifacts


def _summarize_collapsed_stacks(path: Path) -> dict[str, Any]:
    totals: dict[str, float] = {}
    total_samples = 0.0
    for line in path.read_text(errors="ignore").splitlines():
        if not line.strip() or " " not in line:
            continue
        stack, raw_count = line.rsplit(" ", 1)
        try:
            count = float(raw_count)
        except ValueError:
            continue
        function = stack.split(";")[-1].strip() or "unknown"
        totals[function] = totals.get(function, 0.0) + count
        total_samples += count
    return _top_function_summary("collapsed-stacks", totals, total_samples)


def _summarize_text_profile(path: Path) -> dict[str, Any]:
    totals: dict[str, float] = {}
    total_samples = 0.0
    pattern = re.compile(r"(?P<percent>\d+(?:\.\d+)?)%\s+(?P<name>[A-Za-z_][\w./:$<>-]+)")
    for line in path.read_text(errors="ignore").splitlines():
        match = pattern.search(line)
        if not match:
            continue
        value = float(match.group("percent"))
        name = match.group("name")
        totals[name] = max(totals.get(name, 0.0), value)
        total_samples = max(total_samples, 100.0)
    return _top_function_summary("text-profile", totals, total_samples)


def _summarize_speedscope(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {"available": True, "type": "speedscope", "top_functions": [], "warnings": ["invalid speedscope JSON"]}
    frames = payload.get("shared", {}).get("frames", [])
    frame_names = [frame.get("name", f"frame_{index}") for index, frame in enumerate(frames) if isinstance(frame, dict)]
    totals: dict[str, float] = {}
    total_samples = 0.0
    for profile in payload.get("profiles", []):
        if not isinstance(profile, dict):
            continue
        weights = profile.get("weights") or []
        samples = profile.get("samples") or []
        for sample_index, sample in enumerate(samples):
            weight = float(weights[sample_index]) if sample_index < len(weights) and _is_number(weights[sample_index]) else 1.0
            if isinstance(sample, list) and sample:
                frame_index = sample[-1]
                if isinstance(frame_index, int) and 0 <= frame_index < len(frame_names):
                    totals[frame_names[frame_index]] = totals.get(frame_names[frame_index], 0.0) + weight
                    total_samples += weight
    return _top_function_summary("speedscope", totals, total_samples)


def _top_function_summary(profile_type: str, totals: dict[str, float], total_samples: float) -> dict[str, Any]:
    top_functions = []
    for name, value in sorted(totals.items(), key=lambda item: item[1], reverse=True)[:10]:
        top_functions.append(
            {
                "name": name,
                "samples": round(value, 4),
                "percent": round((value / total_samples) * 100, 4) if total_samples else 0,
            }
        )
    return {
        "available": True,
        "type": profile_type,
        "sample_count": round(total_samples, 4),
        "top_functions": top_functions,
        "warnings": [] if top_functions else ["no top functions parsed"],
    }


def _is_number(value: Any) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


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
