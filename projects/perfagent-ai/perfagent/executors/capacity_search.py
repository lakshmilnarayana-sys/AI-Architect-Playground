from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from perfagent.core.artifacts import read_json, write_json


def build_capacity_probe_rps(*, min_rps: int, max_rps: int, steps: int = 6) -> list[int]:
    min_rps = max(1, int(min_rps))
    max_rps = max(min_rps, int(max_rps))
    steps = max(1, int(steps))
    if steps == 1 or min_rps == max_rps:
        return [min_rps]
    if min_rps > 0 and max_rps / min_rps >= steps:
        values: list[int] = []
        current = min_rps
        while current < max_rps and len(values) < steps - 1:
            values.append(current)
            current *= 2
        values.append(max_rps)
        return _dedupe_sorted(values)
    interval = (max_rps - min_rps) / (steps - 1)
    return _dedupe_sorted(round(min_rps + interval * index) for index in range(steps))


def run_capacity_search(
    *,
    service_name: str,
    openapi_path: Path,
    target_url: str,
    runtime: str,
    slo_p95_ms: int,
    slo_error_rate_percent: float,
    duration: str,
    output_dir: Path,
    engine: str = "k6",
    min_rps: int = 50,
    max_rps: int = 800,
    steps: int = 6,
    repeats: int = 1,
    refinement_steps: int = 0,
    fail_fast: bool = True,
    extra_args: list[str] | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    probes: list[dict[str, Any]] = []
    safe_rps = 0
    failing_rps: int | None = None
    for rps in build_capacity_probe_rps(min_rps=min_rps, max_rps=max_rps, steps=steps):
        probe = _run_repeated_probe(
            rps=rps,
            repeats=repeats,
            output_dir=output_dir,
            service_name=service_name,
            openapi_path=openapi_path,
            target_url=target_url,
            runtime=runtime,
            slo_p95_ms=slo_p95_ms,
            slo_error_rate_percent=slo_error_rate_percent,
            duration=duration,
            engine=engine,
            extra_args=extra_args or [],
        )
        probes.append(probe)
        if probe["passed"]:
            safe_rps = max(safe_rps, rps)
        elif failing_rps is None:
            failing_rps = rps
        if fail_fast and not probe["passed"]:
            break

    for _ in range(max(0, int(refinement_steps))):
        if not safe_rps or not failing_rps or failing_rps - safe_rps <= 1:
            break
        rps = (safe_rps + failing_rps) // 2
        probe = _run_repeated_probe(
            rps=rps,
            repeats=repeats,
            output_dir=output_dir,
            service_name=service_name,
            openapi_path=openapi_path,
            target_url=target_url,
            runtime=runtime,
            slo_p95_ms=slo_p95_ms,
            slo_error_rate_percent=slo_error_rate_percent,
            duration=duration,
            engine=engine,
            extra_args=extra_args or [],
            label="refine",
        )
        probes.append(probe)
        if probe["passed"]:
            safe_rps = max(safe_rps, rps)
        else:
            failing_rps = min(failing_rps, rps)

    unstable = any(probe["pass_count"] not in {0, probe["repeat_count"]} for probe in probes)
    result = {
        "mode": "capacity-search",
        "service_name": service_name,
        "engine": engine,
        "min_rps": min_rps,
        "max_rps": max_rps,
        "steps": steps,
        "repeats": max(1, int(repeats)),
        "refinement_steps": max(0, int(refinement_steps)),
        "estimated_capacity_rps": safe_rps,
        "breaking_point_rps": failing_rps,
        "capacity_confidence": _capacity_confidence(safe_rps, failing_rps, repeats, unstable),
        "confidence_interval_rps": {"lower": safe_rps, "upper": failing_rps},
        "unstable_probe_results": unstable,
        "probes": probes,
    }
    write_json(output_dir / "capacity_search.json", result)
    return result


def _run_repeated_probe(
    *,
    rps: int,
    repeats: int,
    output_dir: Path,
    service_name: str,
    openapi_path: Path,
    target_url: str,
    runtime: str,
    slo_p95_ms: int,
    slo_error_rate_percent: float,
    duration: str,
    engine: str,
    extra_args: list[str],
    label: str = "probe",
) -> dict[str, Any]:
    runs = [
        _run_single_probe(
            rps=rps,
            repeat_index=repeat_index,
            output_dir=output_dir,
            service_name=service_name,
            openapi_path=openapi_path,
            target_url=target_url,
            runtime=runtime,
            slo_p95_ms=slo_p95_ms,
            slo_error_rate_percent=slo_error_rate_percent,
            duration=duration,
            engine=engine,
            extra_args=extra_args,
            label=label,
        )
        for repeat_index in range(1, max(1, int(repeats)) + 1)
    ]
    pass_count = sum(1 for run in runs if run["passed"])
    p95_values = [float(run["max_p95_latency_ms"]) for run in runs if run.get("max_p95_latency_ms") is not None]
    error_values = [float(run["max_error_rate_percent"]) for run in runs if run.get("max_error_rate_percent") is not None]
    return {
        "rps": rps,
        "label": label,
        "repeat_count": len(runs),
        "pass_count": pass_count,
        "passed": pass_count == len(runs),
        "decision": "PASS" if pass_count == len(runs) else "WARN" if pass_count else "BLOCK",
        "max_p95_latency_ms": max(p95_values) if p95_values else None,
        "max_error_rate_percent": max(error_values) if error_values else None,
        "runs": runs,
    }


def _run_single_probe(
    *,
    rps: int,
    repeat_index: int,
    output_dir: Path,
    service_name: str,
    openapi_path: Path,
    target_url: str,
    runtime: str,
    slo_p95_ms: int,
    slo_error_rate_percent: float,
    duration: str,
    engine: str,
    extra_args: list[str],
    label: str,
) -> dict[str, Any]:
    probe_dir = output_dir / f"{label}-{rps}rps" / f"run-{repeat_index}"
    command = [
        sys.executable,
        "-m",
        "perfagent",
        "evaluate",
        "--service-name",
        service_name,
        "--openapi",
        str(openapi_path),
        "--target-url",
        target_url,
        "--runtime",
        runtime,
        "--slo-p95-ms",
        str(slo_p95_ms),
        "--slo-error-rate",
        str(slo_error_rate_percent),
        "--duration",
        duration,
        "--engine",
        engine,
        "--mode",
        "capacity",
        "--capacity-probe-rps",
        str(rps),
        "--output",
        str(probe_dir),
        "--no-store",
    ]
    command.extend(extra_args)
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    summary_path = probe_dir / "reports" / "summary.json"
    summary = read_json(summary_path) if summary_path.exists() else {}
    features = summary.get("features", {})
    decision = summary.get("release_decision") or features.get("release_decision") or "UNKNOWN"
    return {
        "rps": rps,
        "repeat_index": repeat_index,
        "probe_dir": str(probe_dir),
        "command": command,
        "exit_code": result.returncode,
        "decision": decision,
        "passed": result.returncode == 0 and decision == "PASS",
        "max_p95_latency_ms": features.get("max_p95_latency_ms"),
        "max_error_rate_percent": features.get("max_error_rate_percent"),
        "summary_path": str(summary_path) if summary_path.exists() else None,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }


def _capacity_confidence(safe_rps: int, failing_rps: int | None, repeats: int, unstable: bool) -> str:
    if not safe_rps:
        return "low"
    if unstable:
        return "medium"
    if failing_rps and repeats >= 2:
        return "high"
    if failing_rps:
        return "medium"
    return "medium"


def _dedupe_sorted(values: Any) -> list[int]:
    return sorted({int(value) for value in values})
