# Local Docker Setup

This setup runs two services:

- Neo4j Browser: http://localhost:7474
- Streamlit demo: http://localhost:8501

## Start

```bash
cd projects/nexusgraph-ai
docker compose up --build
```

Neo4j credentials:

```text
username: neo4j
password: nexusgraph-local
```

## Import The Graph

In a second terminal, after Neo4j is healthy:

```bash
cd projects/nexusgraph-ai
docker compose exec app python src/import_to_neo4j.py
```

## Inspect Local CSV Data

```bash
cd projects/nexusgraph-ai
python3 src/inspect_graph.py
```

## Stop

```bash
cd projects/nexusgraph-ai
docker compose down
```

To remove the Neo4j data volume:

```bash
docker compose down -v
```
