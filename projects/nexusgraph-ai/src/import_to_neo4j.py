from __future__ import annotations

import csv
import os
from pathlib import Path

from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parents[1]
NODE_LABELS = {
    'Person', 'Team', 'Project', 'Service', 'Skill', 'Tool', 'Document',
    'Decision', 'Incident', 'Audit', 'Vendor', 'System'
}


def env(name: str, default: str) -> str:
    return os.getenv(name, default)


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline='') as handle:
        return list(csv.DictReader(handle))


def reset_graph(driver) -> None:
    with driver.session() as session:
        session.run('MATCH (n) DETACH DELETE n')
        session.run('CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (n:Entity) REQUIRE n.id IS UNIQUE')


def create_node(session, row: dict[str, str]) -> None:
    label = row['label']
    if label not in NODE_LABELS:
        raise ValueError(f'Unsupported label: {label}')
    session.run(
        f'MERGE (n:Entity:{label} {{id: $id}}) SET n.name = $name, n.description = $description, n.label = $label',
        id=row['id'], name=row['name'], description=row['description'], label=label,
    )


def create_relationship(session, row: dict[str, str]) -> None:
    relationship = row['relationship']
    if not relationship.replace('_', '').isalpha() or relationship.upper() != relationship:
        raise ValueError(f'Unsupported relationship: {relationship}')
    session.run(
        f"""
        MATCH (source:Entity {{id: $source}})
        MATCH (target:Entity {{id: $target}})
        MERGE (source)-[:{relationship}]->(target)
        """,
        source=row['source'], target=row['target'],
    )


def main() -> None:
    uri = env('NEO4J_URI', 'bolt://localhost:7687')
    username = env('NEO4J_USERNAME', 'neo4j')
    password = env('NEO4J_PASSWORD', 'nexusgraph-local')
    driver = GraphDatabase.driver(uri, auth=(username, password))
    nodes = load_rows(ROOT / 'graph' / 'nodes.csv')
    edges = load_rows(ROOT / 'graph' / 'edges.csv')
    with driver:
        reset_graph(driver)
        with driver.session() as session:
            for row in nodes:
                create_node(session, row)
            for row in edges:
                create_relationship(session, row)
    print(f'Imported {len(nodes)} nodes and {len(edges)} relationships into {uri}.')


if __name__ == '__main__':
    main()
