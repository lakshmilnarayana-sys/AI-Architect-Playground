# Railway Deployment

Use Railway when you want a Docker-based deployment instead of Streamlit
Community Cloud's Python-only runtime.

## App Service

Create a new Railway service from the GitHub repository:

- Repository: `lakshmilnarayana-sys/AI-Architect-Playground`
- Branch: `main`
- Root directory: `projects/nexusgraph-ai`

Railway will use `railway.toml`, build the root `Dockerfile`, and run
`scripts/entrypoint.sh`. The entrypoint imports the graph, ingests the local
Chroma vector store, then starts Streamlit on Railway's injected `PORT`.

## Required Variables

Set these on the app service:

```env
LLM_PROVIDER=groq
GROQ_API_KEY=...

NEO4J_URI=bolt://<neo4j-service-private-domain>:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=...
```

You can also use OpenAI or Gemini instead of Groq:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=...
```

```env
LLM_PROVIDER=gemini
GOOGLE_API_KEY=...
```

Do not use `LLM_PROVIDER=ollama` unless you deploy and configure a separate
Ollama service with enough memory and a reachable private URL.

## Neo4j

Use one of these options:

1. Add a Neo4j service on Railway from the `neo4j:5.26-community` image and set
   the app's `NEO4J_URI` to that service's private domain.
2. Use Neo4j AuraDB and set `NEO4J_URI` to the Aura `neo4j+s://...` URI.

The app imports `graph/nodes.csv` and `graph/edges.csv` at container startup.
For production data, remove the automatic startup import and move ingestion to a
separate one-off job.

## Chroma

This project uses embedded ChromaDB under `vector_store/chroma`; it is not a
separate Chroma server. On Railway, the entrypoint rebuilds that store at
startup from repo data and docs.

## Health Check

`railway.toml` uses Streamlit's health endpoint:

```text
/_stcore/health
```

If the deployment says the application failed to respond, check that the
service root directory is `projects/nexusgraph-ai` and that logs show Streamlit
running on Railway's injected `PORT`.
