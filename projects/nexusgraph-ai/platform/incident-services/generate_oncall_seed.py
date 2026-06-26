"""Build the on-call registry seed JSON from incident-agent ground-truth data."""
import argparse
import csv
import json
from pathlib import Path

import yaml

SEVERITIES = ["SEV1", "SEV2", "SEV3"]


def _load_yaml(path: Path):
    if not path.exists():
        return []
    with path.open() as fh:
        return yaml.safe_load(fh) or []


def _service_short(service_id: str) -> str:
    return service_id.split(":", 1)[1] if ":" in service_id else service_id


def _team_by_service(graph_dir: Path) -> dict[str, str]:
    """service short name -> team display name, from OWNS_SERVICE edges."""
    nodes = {}
    npath, epath = graph_dir / "nodes.csv", graph_dir / "edges.csv"
    if npath.exists():
        with npath.open(newline="") as fh:
            for row in csv.DictReader(fh):
                nodes[row["id"]] = row.get("name", row["id"])
    out = {}
    if epath.exists():
        with epath.open(newline="") as fh:
            for e in csv.DictReader(fh):
                if "OWNS_SERVICE" in (e.get("relationship", "") or "").upper():
                    svc = _service_short(e["target"])
                    out[f"{svc}-service" if not svc.endswith("-service") else svc] = nodes.get(e["source"], e["source"])
    return out


def build_seed(data_dir: Path, graph_dir: Path) -> dict:
    teams = _team_by_service(graph_dir)
    schedules = _load_yaml(data_dir / "oncall_schedules.yaml")
    policies = _load_yaml(data_dir / "escalation_policies.yaml")

    oncall = {}
    for svc, team in teams.items():
        sched = None
        person = None
        token = svc.replace("-service", "")
        for s in schedules:
            blob = (str(s.get("name", "")) + " " + str(s.get("team", "")) + " " + str(s.get("service", ""))).lower()
            if token in blob or (team and team.lower() in blob):
                sched = s.get("name")
                person = s.get("primary") or s.get("oncall") or (s.get("rotation", [{}])[0].get("person") if s.get("rotation") else None)
                break
        oncall[svc] = {"schedule": sched or f"{team} On-Call", "person": person, "team": team}

    escalation = {}
    for svc in teams:
        token = svc.replace("-service", "")
        for sev in SEVERITIES:
            policy = None
            steps = []
            for p in policies:
                blob = (str(p.get("name", "")) + " " + str(p.get("description", ""))).lower()
                if token in blob and sev.lower() in blob:
                    policy = p.get("name")
                    steps = p.get("steps") or ["primary-oncall", "secondary-oncall", "engineering-manager"]
                    break
            if policy:
                escalation[f"{svc}|{sev}"] = {"policy": policy, "steps": steps}
    return {"oncall": oncall, "escalation": escalation}


def main(out: str, data_dir: str, graph_dir: str) -> None:
    seed = build_seed(Path(data_dir), Path(graph_dir))
    Path(out).write_text(json.dumps(seed, indent=2))
    print(f"wrote {out}: {len(seed['oncall'])} oncall, {len(seed['escalation'])} escalation")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="oncall-seed.json")
    ap.add_argument("--data", default="../../data")
    ap.add_argument("--graph", default="../../graph")
    a = ap.parse_args()
    main(a.out, a.data, a.graph)
