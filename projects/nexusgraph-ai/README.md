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


## Architecture Diagram

![nexusgraph-ai service traffic flow](architecture-flow-simple.png)

A simpler static traffic-flow diagram. Detailed diagram source remains available as [`architecture-diagram.svg`](architecture-diagram.svg) and [`docs/architecture-diagram.mmd`](docs/architecture-diagram.mmd).

## Dataset

The project uses a fictional streaming company dataset:

```text
StreamFlix Organizational Knowledge Dataset
```

The current seed graph contains people, teams, projects, services, skills, tools, documents, decisions, incidents, audits, vendors, systems, on-call schedules, current on-call assignments, dashboards, runbooks, escalation policies, SLO metrics, datastores, event topics, architecture docs, OpenAPI specs, Kubernetes manifests, and Terraform references. It also incorporates missing service-dependency and operational documentation concepts from the Netflix synthetic service dataset. Source artifacts live in `data/`, while graph import artifacts live in `graph/`.

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



## Vector Database

The Vector RAG baseline uses ChromaDB as a local persistent vector database. Chroma keeps the local setup simple: no external API keys, no managed service dependency, and a persistent store under `vector_store/chroma`.

Dry-run document preparation:

```bash
cd projects/nexusgraph-ai
docker compose exec app python src/vector_ingest.py --dry-run
```

Ingest into ChromaDB:

```bash
docker compose exec app python src/vector_ingest.py
```

Query the vector store:

```bash
docker compose exec app python src/vector_query.py "Who is on call for playback-service?" --n-results 5
```

The initial ingestion includes graph nodes, graph relationships, YAML source data, docs, and evaluation artifacts.

## Next Implementation Steps

1. Add a Vector RAG answer wrapper over the ChromaDB retrieval results.
2. Add Cypher-backed GraphRAG query functions for the 10 evaluation queries.
3. Compare Vector RAG and GraphRAG results in `evaluation/results.md`.
4. Record the demo using the local Docker environment.
