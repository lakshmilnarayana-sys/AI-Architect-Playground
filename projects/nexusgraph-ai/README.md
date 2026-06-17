# nexusgraph-ai

GraphRAG for Organizational Knowledge and Decision Intelligence.

`nexusgraph-ai` models organizational knowledge as a graph of people, teams, services, runbooks, dashboards, SLOs, on-call schedules, documents, decisions, audits, and incidents. It uses GraphRAG to answer relationship-heavy operational questions that traditional Vector RAG struggles with, such as who owns a service, who is on call, which runbook applies, which dashboard/SLO matters, and which dependencies are involved.

## Requirements

- Docker Desktop or Docker Engine with Docker Compose.
- Python 3.12 if you install dependencies locally outside Docker. Python 3.14
  can force source builds for dependencies such as `pyarrow`, which is pulled
  in by Streamlit.
- Enough disk space for the Python image, Neo4j volume, ChromaDB store, and the local Ollama model.
- Optional hosted LLM API key only if you choose `openai`, `gemini`, or `groq` instead of local Ollama.

## Local Python Environment

The app is pinned to Python 3.12 for Docker and Streamlit Community Cloud. If
Homebrew's default `python3` points at a newer runtime, create the virtualenv
with an explicit 3.12 interpreter:

```bash
/opt/homebrew/bin/python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Quick Start With Docker

From the repository root:

```bash
cd projects/nexusgraph-ai
cp .env.example .env
```

If you are already inside this project directory:

```bash
cp .env.example .env
```

For the simplest fully local run, set the LLM provider in `.env` to Ollama:

```env
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3
```

Start the full stack:

```bash
docker compose up -d neo4j ollama
```

On first run, download the local Ollama model:

```bash
docker compose exec ollama ollama pull llama3
```

Build and start the app:

```bash
docker compose up -d --build app
```

The `app` container automatically imports the Neo4j graph and ingests ChromaDB
documents before starting Streamlit. You do not need to run graph or vector
ingestion manually for the normal demo path.

Open these local URLs:

- Streamlit app: http://localhost:8501
- Neo4j Browser: http://localhost:7474
- Ollama API: http://localhost:11434

Neo4j credentials:

```text
username: neo4j
password: nexusgraph-local
```

Security defaults:

- Docker ports bind to `127.0.0.1` only, so Streamlit, Neo4j, and Ollama are
  reachable from your machine but not from the wider network.
- The Streamlit query input is capped at 500 characters to reduce accidental or
  abusive prompt/API usage.
- `.env` is ignored by Git. Do not commit real hosted LLM API keys.
- For anything beyond a local demo, set a non-default `NEO4J_PASSWORD` in `.env`.
  If you change the Neo4j password after the database volume already exists,
  recreate the volume with `docker compose down -v` before starting again.
- See [`SECURITY.md`](SECURITY.md) for repo security notes and local-demo
  boundaries.

Check container status:

```bash
docker compose ps
```

Follow app logs:

```bash
docker compose logs -f app
```

Stop the stack:

```bash
docker compose down
```

Remove local Docker volumes as well:

```bash
docker compose down -v
```

## Deploy To Streamlit Community Cloud

See [`docs/streamlit-cloud.md`](docs/streamlit-cloud.md) for the hosted
deployment settings, required secrets, and first-deploy data import flow.

## Deploy To Railway

See [`docs/railway.md`](docs/railway.md) for the Docker-based Railway setup,
required variables, and Neo4j service options.

## Architecture Diagram

![nexusgraph-ai service traffic flow](architecture-flow-simple.png)

A simpler static traffic-flow diagram. Detailed diagram source remains available as [`architecture-diagram.svg`](architecture-diagram.svg) and [`docs/architecture-diagram.mmd`](docs/architecture-diagram.mmd).

## Dataset

The project uses a fictional streaming company dataset:

```text
StreamFlix Organizational Knowledge Dataset
```

The current seed graph contains people, teams, projects, services, skills, tools, documents, decisions, incidents, audits, vendors, systems, on-call schedules, current on-call assignments, dashboards, runbooks, escalation policies, SLO metrics, datastores, event topics, architecture docs, OpenAPI specs, Kubernetes manifests, and Terraform references. It also incorporates missing service-dependency and operational documentation concepts from the Netflix synthetic service dataset. Source artifacts live in `data/`, while graph import artifacts live in `graph/`.

## Week 3 Agentic AI Systems

This repo now implements two Week 3 project tracks on top of the StreamFlix operations graph:

1. **Multi-Agent IT Support / Incident Response Agent**: a Freshworks-style incident lifecycle simulation covering identification, logging, categorization, prioritization, response, escalation, diagnosis, recovery, closure, and post-incident review. The demo can inject Kubernetes failure modes for `oom_kill`, `pod_restart`, `disk_iops`, and `cpu_throttle`; the agents attach Kubernetes KV context, static production logs, observability evidence, mitigation plans, recovery checks, and postmortem actions.
2. **Intelligent Project Status Agent**: a weekly status synthesis agent over synthetic Jira, GitHub, dependency, risk, blocker, and decision snapshots. It produces a status color, executive summary, risks, blockers, dependencies, week-over-week insights, and next actions.

The incident simulation uses local deterministic data rather than touching a live cluster. Kubernetes resources live in `data/kubernetes_resources.yaml`; static logs live in `data/service_logs.yaml`; outage scenarios live in `data/incident_scenarios.yaml`; FireHydrant-style runbook automation lives in `data/firehydrant_runbook_automations.yaml`.

Recommended production integrations are modeled in `data/observability_sources.yaml`: OpenSearch with Fluent Bit for external log collection, and Grafana Cloud with Prometheus, Loki, Tempo, and Alertmanager for observability. The Streamlit UI also includes a Streamflix status-history surface inspired by public SaaS status pages.

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



## Manual Data Commands

The Vector RAG baseline uses ChromaDB as a local persistent vector database.
Chroma keeps the local setup simple: no managed vector database is required, and
the persistent store lives under `vector_store/chroma`.

The Docker entrypoint already runs these ingestion commands. Use the manual
commands below only when you want to re-run a specific step inside an already
running container.

Import the graph into Neo4j:

```bash
docker compose exec app python src/import_to_neo4j.py
```

Dry-run document preparation:

```bash
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

Generate a readable Vector RAG answer from retrieved chunks:

```bash
docker compose exec app python src/vector_rag.py "Who is on call for playback-service?" --n-results 5
```

The initial ingestion includes graph nodes, graph relationships, YAML source data, docs, and evaluation artifacts.

## Run Checks

Run the current test suite inside the app container:

```bash
docker compose exec app python -m unittest \
  tests.test_hybrid_rag \
  tests.test_software_catalog \
  tests.test_streamlit_ui_static \
  tests.test_ui_trace \
  tests.test_vector_query \
  tests.test_vector_rag \
  tests.test_vector_ingestion \
  tests.test_vector_ingestion_new
```

Compile-check the main app and helper modules:

```bash
docker compose exec app python -m py_compile \
  app/streamlit_app.py \
  src/hybrid_rag.py \
  src/vector_query.py \
  src/software_catalog.py \
  src/ui_trace.py
```

## Optional Hosted LLM Providers

The app can also use hosted LLM providers. Set `LLM_PROVIDER` in `.env` to one
of `openai`, `gemini`, or `groq`, then provide the matching API key:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=...
```

```env
LLM_PROVIDER=gemini
GOOGLE_API_KEY=...
```

```env
LLM_PROVIDER=groq
GROQ_API_KEY=...
```

Restart the app after changing `.env`:

```bash
docker compose restart app
```

## Current Implementation Notes

The Streamlit demo includes:

1. GraphRAG and Vector RAG side-by-side comparison.
2. Collapsed JSON response expanders for each answer panel.
3. Behind-the-scenes trace timelines and evidence cards.
4. Neo4j graph import and ChromaDB vector ingestion during container startup.
5. A software catalog explorer and graph preview for the synthetic Streamflix dataset.
6. A production-like incident response simulation with Kubernetes failure injection, static logs, observability evidence, FireHydrant-style automation, and Freshworks-style lifecycle checkpoints.
7. A Streamflix status page with active incident and incident history.
8. A project status agent that summarizes weekly risks, blockers, dependencies, and next actions.
