from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOTS_PATH = ROOT / "data" / "project_status_snapshots.yaml"


def load_project_snapshots(path: Path = SNAPSHOTS_PATH) -> list[dict]:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or []


def get_project_snapshot(project_name: str, path: Path = SNAPSHOTS_PATH) -> dict:
    for project in load_project_snapshots(path):
        if project["project"] == project_name:
            return project
    raise KeyError(f"Unknown project: {project_name}")
