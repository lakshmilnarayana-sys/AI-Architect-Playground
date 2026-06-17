from __future__ import annotations

import argparse
import json
from pathlib import Path

import chromadb

try:
    from config import DEFAULT_CHROMA_PATH, DEFAULT_COLLECTION
    from incident.jira import seed_incident_history
    from incident.scenarios import load_scenarios
except ModuleNotFoundError:
    from src.config import DEFAULT_CHROMA_PATH, DEFAULT_COLLECTION
    from src.incident.jira import seed_incident_history
    from src.incident.scenarios import load_scenarios


def seed_vector_store(force: bool = False) -> dict:
    try:
        from vector_ingest import ingest_documents
    except ModuleNotFoundError:
        from src.vector_ingest import ingest_documents

    ready = False
    if DEFAULT_CHROMA_PATH.exists() and not force:
        try:
            chromadb.PersistentClient(path=str(DEFAULT_CHROMA_PATH)).get_collection(DEFAULT_COLLECTION)
            ready = True
        except Exception:
            ready = False

    if ready:
        return {
            "status": "existing",
            "collection": DEFAULT_COLLECTION,
            "persist_path": str(DEFAULT_CHROMA_PATH),
        }
    result = ingest_documents()
    return {"status": "seeded", **result}


def seed_neo4j_graph(enabled: bool = False) -> dict:
    if not enabled:
        return {"status": "skipped"}
    try:
        try:
            from import_to_neo4j import main as import_to_neo4j
        except ModuleNotFoundError:
            from src.import_to_neo4j import main as import_to_neo4j

        import_to_neo4j()
        return {"status": "seeded"}
    except Exception as exc:
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}


def seed_fallback_stores() -> dict:
    Path("var").mkdir(parents=True, exist_ok=True)
    jira = seed_incident_history(load_scenarios())
    return {"status": "seeded", "jira": jira}


def seed_all(seed_neo4j: bool = False, force_vector: bool = False) -> dict:
    return {
        "vector_store": seed_vector_store(force=force_vector),
        "neo4j_graph": seed_neo4j_graph(enabled=seed_neo4j),
        "fallback_stores": seed_fallback_stores(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed nexusgraph-ai runtime data stores.")
    parser.add_argument("--neo4j", action="store_true", help="Import graph/nodes.csv and graph/edges.csv into Neo4j.")
    parser.add_argument("--force-vector", action="store_true", help="Recreate the Chroma vector store.")
    args = parser.parse_args()
    print(json.dumps(seed_all(seed_neo4j=args.neo4j, force_vector=args.force_vector), indent=2))


if __name__ == "__main__":
    main()
