#!/bin/bash
set -e

echo "--- Starting Fresh Ingestion ---"

# 1. Import data to Neo4j
echo "Importing nodes and edges to Neo4j..."
python3 src/import_to_neo4j.py

# 2. Ingest documents to ChromaDB
echo "Ingesting documents to ChromaDB..."
python3 src/vector_ingest.py

echo "--- Ingestion Complete ---"

# 3. Start Streamlit
echo "Starting Streamlit app..."
APP_PORT=${PORT:-8501}
exec streamlit run app/streamlit_app.py --server.address=0.0.0.0 --server.port=${APP_PORT} --server.headless=true
