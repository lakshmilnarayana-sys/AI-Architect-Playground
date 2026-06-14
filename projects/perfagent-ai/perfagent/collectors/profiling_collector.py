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
