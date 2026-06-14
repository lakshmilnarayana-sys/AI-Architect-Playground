from pathlib import Path
import csv

import yaml

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
GRAPH = ROOT / "graph"


def _load_yaml(name: str) -> list[dict]:
    path = DATA / name
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or []


def _keyword_match(haystack: str, needle: str) -> bool:
    h = (haystack or "").lower()
    return any(tok in h for tok in needle.lower().split())


class GraphContext:
    """Read-only grounding over the knowledge graph with CSV/YAML fallback.

    With ``use_neo4j=True`` lookups try the live graph via
    ``hybrid_rag.query_graph_with_retry`` and fall back to ``data/*.yaml`` and
    ``graph/{nodes,edges}.csv`` on any failure. Tests use ``use_neo4j=False``.
    """

    def __init__(self, use_neo4j: bool = True):
        self.use_neo4j = use_neo4j

    # --- Neo4j attempt with safe fallback ------------------------------------
    def _neo4j(self, cypher: str):
        if not self.use_neo4j:
            return None
        try:
            from src.hybrid_rag import query_graph_with_retry
            rows, _attempts, _source = query_graph_with_retry(cypher)
            return rows
        except Exception:
            return None

    # --- Public lookups ------------------------------------------------------
    def runbooks_for(self, service: str) -> list[dict]:
        token = service.split()[0]
        rows = self._neo4j(
            f"MATCH (r:Runbook) WHERE r.name =~ '(?i).*{token}.*' "
            f"RETURN r.id AS id, r.name AS name LIMIT 10"
        )
        if rows:
            return [{"id": r.get("id"), "name": r.get("name")} for r in rows]
        return [
            {"id": r["id"], "name": r.get("name")}
            for r in _load_yaml("runbooks.yaml")
            if token.lower() in (r.get("name", "") + r.get("id", "")).lower()
        ]

    def escalation_for(self, service: str, severity: str) -> dict | None:
        policies = _load_yaml("escalation_policies.yaml")
        sev = severity.lower()
        token = service.split()[0].lower()
        for p in policies:
            blob = (p.get("name", "") + " " + p.get("description", "")).lower()
            if token in blob and sev in blob:
                return {"id": p["id"], "name": p.get("name")}
        for p in policies:
            if token in (p.get("name", "") + p.get("description", "")).lower():
                return {"id": p["id"], "name": p.get("name")}
        return None

    def slo_for(self, service: str) -> list[dict]:
        return [s for s in _load_yaml("slo_metrics.yaml") if _keyword_match(s.get("name", ""), service)]

    def owner_for(self, service: str) -> dict | None:
        return self._edge_target(service, ("OWNS_SERVICE", "OWNED_BY"))

    def oncall_for(self, service: str) -> dict | None:
        return self._edge_target(service, ("HAS_ONCALL_SCHEDULE", "ON_CALL"))

    # --- CSV edge traversal fallback -----------------------------------------
    def _edge_target(self, service: str, rel_types: tuple[str, ...]) -> dict | None:
        edges_path = GRAPH / "edges.csv"
        nodes_path = GRAPH / "nodes.csv"
        if not edges_path.exists() or not nodes_path.exists():
            return None
        with open(nodes_path, newline="", encoding="utf-8") as fh:
            nodes = {row["id"]: row for row in csv.DictReader(fh)}
        token = service.split()[0].lower()
        svc_ids = {
            nid for nid, n in nodes.items()
            if token in (n.get("name", "") + n.get("id", "")).lower()
        }
        with open(edges_path, newline="", encoding="utf-8") as fh:
            for e in csv.DictReader(fh):
                rel = (e.get("relationship", "") or "").upper()
                if any(rt in rel for rt in rel_types):
                    if e.get("source") in svc_ids and e.get("target") in nodes:
                        return {"id": e["target"], "name": nodes[e["target"]].get("name")}
                    if e.get("target") in svc_ids and e.get("source") in nodes:
                        return {"id": e["source"], "name": nodes[e["source"]].get("name")}
        return None
