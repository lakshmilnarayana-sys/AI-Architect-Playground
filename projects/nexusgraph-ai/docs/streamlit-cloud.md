# Streamlit Community Cloud Deployment

Use this guide to deploy the hosted demo from the monorepo.

## Streamlit App Settings

- Repository: `lakshmilnarayana-sys/AI-Architect-Playground`
- Branch: `main`
- Main file path: `projects/nexusgraph-ai/app/streamlit_app.py`
- Python version: `3.12`

The entrypoint directory includes `app/requirements.txt`, which points Streamlit
Cloud back to the project-level `requirements.txt`.

## Required Hosted Services

Streamlit Community Cloud does not run this project's Docker Compose services.
Use hosted services instead:

- Neo4j Aura or another network-reachable Neo4j instance.
- A hosted LLM provider such as Groq, OpenAI, or Gemini.

Do not use `LLM_PROVIDER=ollama` on Streamlit Cloud unless you provide a
separately hosted Ollama endpoint.

## Streamlit Secrets

Paste this into Streamlit Cloud **Advanced settings -> Secrets** and replace the
placeholder values:

```toml
LLM_PROVIDER = "groq"
GROQ_API_KEY = "..."

NEO4J_URI = "neo4j+s://your-aura-instance.databases.neo4j.io"
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = "..."

# Set this to true on first deploy, or whenever you intentionally want the
# app to reset and reload the synthetic graph into the configured Neo4j DB.
NEXUSGRAPH_AUTO_IMPORT_NEO4J = "true"
```

After the first successful deploy, change `NEXUSGRAPH_AUTO_IMPORT_NEO4J` to
`"false"` unless you want every cold start to reset the hosted Neo4j graph.

## Startup Behavior

On startup, the app:

1. Copies Streamlit secrets into environment variables before backend modules
   initialize.
2. Builds the local Chroma vector store if the expected collection is missing.
3. Optionally imports the synthetic graph into Neo4j when
   `NEXUSGRAPH_AUTO_IMPORT_NEO4J` is truthy.

## Smoke Test

After deployment:

1. Open the app URL.
2. Open **Ask NexusGraph**.
3. Run the first curated query.
4. Confirm both answer panels render without backend errors.
5. Confirm **JSON response** is collapsed by default.
6. Open Streamlit logs and check for missing dependencies, Neo4j connection
   errors, or LLM authentication errors.
