# Local Docker Setup

This setup runs three services:

- Neo4j Browser: http://localhost:7474
- Streamlit demo: http://localhost:8501
- Ollama API: http://localhost:11434

## Start

From the repository root:

```bash
cd projects/nexusgraph-ai
cp .env.example .env
```

For a fully local run, use Ollama in `.env`:

```env
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3
```

Start Neo4j and Ollama first:

```bash
docker compose up -d neo4j ollama
```

Download the local model on first run:

```bash
docker compose exec ollama ollama pull llama3
```

Build and start the app:

```bash
docker compose up -d --build app
```

Neo4j credentials:

```text
username: neo4j
password: nexusgraph-local
```

Security defaults:

- Streamlit, Neo4j, and Ollama ports are bound to `127.0.0.1` only.
- `.env` is ignored by Git and should hold any real hosted LLM API keys.
- For non-demo use, set a non-default `NEO4J_PASSWORD` in `.env`.
- If you change `NEO4J_PASSWORD` after Neo4j has initialized, recreate the
  local volume with `docker compose down -v`.

## Ingestion

The app container automatically imports the Neo4j graph and ingests ChromaDB
documents before starting Streamlit.

To rerun graph import manually:

```bash
docker compose exec app python src/import_to_neo4j.py
```

To rerun vector ingestion manually:

```bash
docker compose exec app python src/vector_ingest.py
```

## Inspect Local CSV Data

```bash
docker compose exec app python src/inspect_graph.py
```

## Logs And Status

```bash
docker compose ps
docker compose logs -f app
```

## Stop

```bash
docker compose down
```

To remove local Docker volumes:

```bash
docker compose down -v
```
