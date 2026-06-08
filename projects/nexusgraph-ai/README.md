# nexusgraph-ai

GraphRAG for Organizational Knowledge and Decision Intelligence.

`nexusgraph-ai` models organizational knowledge as a graph of people, teams, projects, services, documents, decisions, tools, audits, and incidents. It uses GraphRAG to answer relationship-heavy questions that traditional vector RAG struggles with, such as identifying who worked on a compliance audit, which tools were used, what decisions were made, and who approved them.

## Local Docker Setup

```bash
cd projects/nexusgraph-ai
docker compose up --build
```

Open:

- Streamlit app: http://localhost:8501
- Neo4j Browser: http://localhost:7474

Neo4j credentials:

```text
username: neo4j
password: nexusgraph-local
```

Import the graph after the containers are healthy:

```bash
docker compose exec app python src/import_to_neo4j.py
```

## Dataset

The project uses a fictional streaming company dataset:

```text
StreamFlix Organizational Knowledge Dataset
```

The current seed graph contains people, teams, projects, services, skills, tools, documents, decisions, incidents, audits, vendors, and systems. Source artifacts live in `data/`, while graph import artifacts live in `graph/`.

## Deliverables

```text
README.md
Dockerfile
docker-compose.yml
.env.example
requirements.txt
data/
graph/
src/
app/
evaluation/
docs/
```

## Next Implementation Steps

1. Add Cypher-backed GraphRAG query functions for the 10 evaluation queries.
2. Add a vector RAG baseline over the same dataset.
3. Capture comparison results in `evaluation/results.md`.
4. Record the demo using the local Docker environment.
