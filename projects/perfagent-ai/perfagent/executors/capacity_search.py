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
    fail_fast: bool = True,
    extra_args: list[str] | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    probes: list[dict[str, Any]] = []
    for rps in build_capacity_probe_rps(min_rps=min_rps, max_rps=max_rps, steps=steps):
        probe_dir = output_dir / f"probe-{rps}rps"
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
        command.extend(extra_args or [])
        result = subprocess.run(command, text=True, capture_output=True, check=False)
        summary_path = probe_dir / "reports" / "summary.json"
        summary = read_json(summary_path) if summary_path.exists() else {}
        features = summary.get("features", {})
        decision = summary.get("release_decision") or features.get("release_decision") or "UNKNOWN"
        probe = {
            "rps": rps,
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
        probes.append(probe)
        if fail_fast and not probe["passed"]:
            break
    safe = [probe for probe in probes if probe["passed"]]
    failing = next((probe for probe in probes if not probe["passed"]), None)
    result = {
        "mode": "capacity-search",
        "service_name": service_name,
        "engine": engine,
        "min_rps": min_rps,
        "max_rps": max_rps,
        "steps": steps,
        "estimated_capacity_rps": max((probe["rps"] for probe in safe), default=0),
        "breaking_point_rps": failing["rps"] if failing else None,
        "capacity_confidence": "high" if safe and failing else "medium" if safe else "low",
        "probes": probes,
    }
    write_json(output_dir / "capacity_search.json", result)
    return result


def _dedupe_sorted(values: Any) -> list[int]:
    return sorted({int(value) for value in values})
