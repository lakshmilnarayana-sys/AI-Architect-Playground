"""Generate Backstage catalog entities from the StreamFlix graph CSVs."""
import argparse
import csv
import io
from pathlib import Path

import yaml

SYSTEM = "streamflix"
DEFAULT_OWNER = "platform-engineering"

# Known per-service failure mode → runbook slug (services that model a failure mode).
RUNBOOK_BY_SERVICE = {
    "playback-service": "cpu_throttle",
    "billing-service": "oom_kill",
    "identity-service": "image_pull_backoff",
    "recommendation-service": "memory_leak",
    "observability-service": "high_error_rate",
}


def _short(node_id: str) -> str:
    return node_id.split(":", 1)[1] if ":" in node_id else node_id


def _k8s_name(short: str) -> str:
    return short if short.endswith("-service") else f"{short}-service"


def load_nodes(path: Path) -> dict:
    out = {}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            out[row["id"]] = row
    return out


def load_edges(path: Path) -> list:
    out = []
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            out.append((row["source"], row["relationship"], row["target"]))
    return out


def build_entities(nodes: dict, edges: list) -> list:
    services = {nid: n for nid, n in nodes.items() if n.get("label") == "Service"}
    teams = {nid: n for nid, n in nodes.items() if n.get("label") == "Team"}
    people = {nid: n for nid, n in nodes.items() if n.get("label") == "Person"}

    owner_of = {}      # service_id -> team_short
    depends = {}       # service_id -> [component names]
    member_of = {}     # person_id -> [group shorts]
    for src, rel, tgt in edges:
        rel_u = rel.upper()
        if rel_u == "OWNS_SERVICE":
            owner_of[tgt] = _short(src)
        elif rel_u == "DEPENDS_ON":
            depends.setdefault(src, []).append(f"component:{_k8s_name(_short(tgt))}")
        elif rel_u == "MEMBER_OF":
            member_of.setdefault(src, []).append(_short(tgt))

    entities = []
    entities.append({
        "apiVersion": "backstage.io/v1alpha1",
        "kind": "System",
        "metadata": {"name": SYSTEM, "description": "StreamFlix streaming platform"},
        "spec": {"owner": f"group:{DEFAULT_OWNER}"},
    })
    for tid, t in teams.items():
        entities.append({
            "apiVersion": "backstage.io/v1alpha1",
            "kind": "Group",
            "metadata": {"name": _short(tid), "description": t.get("description", "")},
            "spec": {"type": "team", "profile": {"displayName": t.get("name", _short(tid))}, "children": []},
        })
    for pid, p in people.items():
        entities.append({
            "apiVersion": "backstage.io/v1alpha1",
            "kind": "User",
            "metadata": {"name": _short(pid), "description": p.get("description", "")},
            "spec": {"profile": {"displayName": p.get("name", _short(pid))}, "memberOf": member_of.get(pid, [])},
        })
    for sid, s in services.items():
        name = _k8s_name(_short(sid))
        owner = owner_of.get(sid, DEFAULT_OWNER)
        tier = (s.get("description") or "internal").strip()
        tag = "customer-facing" if tier == "customer-facing" else "internal"
        annotations = {
            "prometheus.io/service": name,
            "streamflix.io/grafana": f"http://localhost:3000/explore?query=rate(http_requests_total%7Bservice%3D%22{name}%22%7D%5B5m%5D)",
        }
        if name in RUNBOOK_BY_SERVICE:
            annotations["streamflix.io/runbook"] = f"platform/runbooks/{RUNBOOK_BY_SERVICE[name]}.md"
        spec = {
            "type": "service",
            "lifecycle": "production",
            "owner": f"group:{owner}",
            "system": SYSTEM,
        }
        deps = sorted(set(depends.get(sid, [])))
        if deps:
            spec["dependsOn"] = deps
        entities.append({
            "apiVersion": "backstage.io/v1alpha1",
            "kind": "Component",
            "metadata": {"name": name, "description": f"StreamFlix {name}", "tags": [tag], "annotations": annotations},
            "spec": spec,
        })
    return entities


def validate(entities: list) -> list:
    problems = []
    comp_names = {e["metadata"]["name"] for e in entities if e["kind"] == "Component"}
    group_names = {e["metadata"]["name"] for e in entities if e["kind"] == "Group"}
    for e in entities:
        name = e["metadata"]["name"]
        if not name.islower() or " " in name:
            problems.append(f"{e['kind']} name not backstage-valid: {name}")
        if e["kind"] == "Component":
            owner = e["spec"].get("owner", "")
            if not owner.startswith("group:") or owner.split(":", 1)[1] not in group_names:
                problems.append(f"Component {name} owner missing/unknown: {owner}")
            for dep in e["spec"].get("dependsOn", []):
                target = dep.split(":", 1)[1]
                if target not in comp_names:
                    problems.append(f"Component {name} dependsOn unknown component: {target}")
        if e["kind"] == "User":
            for grp in e["spec"].get("memberOf", []):
                if grp not in group_names:
                    problems.append(f"User {name} memberOf unknown group: {grp}")
    return problems


def render(entities: list) -> str:
    buf = io.StringIO()
    yaml.safe_dump_all(entities, buf, sort_keys=False, default_flow_style=False)
    return buf.getvalue()


def main(out: str, nodes_path: str, edges_path: str) -> None:
    nodes = load_nodes(Path(nodes_path))
    edges = load_edges(Path(edges_path))
    entities = build_entities(nodes, edges)
    problems = validate(entities)
    if problems:
        raise SystemExit("catalog validation failed:\n" + "\n".join(problems))
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render(entities))
    print(f"wrote {out} with {len(entities)} entities")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="catalog/catalog.yaml")
    ap.add_argument("--nodes", default="../../graph/nodes.csv")
    ap.add_argument("--edges", default="../../graph/edges.csv")
    a = ap.parse_args()
    main(a.out, a.nodes, a.edges)
