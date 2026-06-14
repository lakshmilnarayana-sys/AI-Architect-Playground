from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any


def collect_profiling_artifacts(profile_paths: list[Path], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[str] = []
    warnings: list[str] = []
    for profile_path in profile_paths:
        if not profile_path.exists():
            warnings.append(f"Profiling artifact not found: {profile_path}")
            continue
        destination = output_dir / profile_path.name
        shutil.copyfile(profile_path, destination)
        artifacts.append(str(destination))
    return {
        "enabled": bool(profile_paths),
        "artifacts": artifacts,
        "warnings": warnings,
        "supported_formats": ["pprof", "jfr", "py-spy", "clinic", "collapsed-stacks", "speedscope"],
    }
