#!/bin/bash
set -e

echo "--- Starting Fresh Ingestion ---"

echo "Seeding Neo4j graph, Chroma vector store, and fallback simulation stores..."
python3 src/seed_runtime_data.py --neo4j --force-vector

echo "--- Ingestion Complete ---"

echo "Starting Streamlit app..."
APP_PORT=${PORT:-8501}
exec streamlit run app/streamlit_app.py --server.address=0.0.0.0 --server.port=${APP_PORT} --server.headless=true
