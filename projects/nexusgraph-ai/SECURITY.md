# Security Notes

This project is a local demo for GraphRAG over synthetic operational data. It is
not configured as a public multi-user service.

## Secrets

- Keep real provider keys only in `.env`.
- `.env` is ignored by Git and excluded from the Docker build context.
- Do not share `docker compose config` output when real keys are present,
  because Compose expands `.env` values into that output.

## Local Exposure

Docker Compose binds Streamlit, Neo4j, and Ollama ports to `127.0.0.1` only:

- Streamlit: `127.0.0.1:8501`
- Neo4j Browser: `127.0.0.1:7474`
- Neo4j Bolt: `127.0.0.1:7687`
- Ollama API: `127.0.0.1:11434`

Do not change these bindings to `0.0.0.0` unless you also add proper network
controls, authentication, rate limiting, and secret management.

## Abuse Controls

- Streamlit query input is capped at 500 characters.
- Neo4j write/destructive Cypher clauses are rejected before generated graph
  queries execute.
- The demo uses static synthetic data and should not be pointed at production
  data without a separate security review.
