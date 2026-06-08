from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Vector Store Config
DEFAULT_CHROMA_PATH = ROOT / 'vector_store' / 'chroma'
DEFAULT_COLLECTION = 'nexusgraph_ai_knowledge'
EMBEDDING_MODEL = 'sentence-transformers/all-MiniLM-L6-v2'
VECTOR_DIMENSIONS = 384

# Sources
SOURCE_GLOBS = [
    'data/*.yaml',
    'docs/*.md',
    'evaluation/*.json',
]

# Neo4j Config (Defaults)
DEFAULT_NEO4J_URI = 'bolt://localhost:7687'
DEFAULT_NEO4J_USERNAME = 'neo4j'
DEFAULT_NEO4J_PASSWORD = 'nexusgraph-local'
