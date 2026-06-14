from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS_PATH = ROOT / "data" / "incident_scenarios.yaml"


def load_scenarios(path: Path = SCENARIOS_PATH) -> list[dict]:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or []


def get_scenario(scenario_id: str, path: Path = SCENARIOS_PATH) -> dict:
    for scenario in load_scenarios(path):
        if scenario["id"] == scenario_id:
            return scenario
    raise KeyError(f"Unknown scenario: {scenario_id}")
