"""Central configuration: paths, role-based access matrix, demo users, model names."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "db" / "mediassist.db"
CHUNKS_PATH = DATA_DIR / "processed" / "chunks.json"
QDRANT_PATH = PROJECT_ROOT / "qdrant_storage"

COLLECTION_NAME = "mediassist_docs"

# Embedding / reranking models (all run locally via fastembed)
DENSE_MODEL = "BAAI/bge-small-en-v1.5"
SPARSE_MODEL = "Qdrant/bm25"
RERANK_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"

# Hybrid retrieval parameters
CANDIDATES_PER_LEG = 10   # broad candidate set fetched per search leg
RERANK_TOP_K = 3          # narrowed set passed to the LLM

# LLM (cloud-hosted inference via OpenAI)
LLM_MODEL = "gpt-4o-mini"

# Which document collections each role may retrieve from.
# This drives the access_roles metadata written at ingestion time AND the
# Qdrant filter applied at query time.
ROLE_COLLECTIONS: dict[str, list[str]] = {
    "doctor": ["general", "clinical", "nursing"],
    "nurse": ["general", "nursing"],
    "billing_executive": ["general", "billing"],
    "technician": ["general", "equipment"],
    "admin": ["general", "clinical", "nursing", "billing", "equipment"],
}

# Inverse view: which roles may access each document collection.
COLLECTION_ROLES: dict[str, list[str]] = {
    "general": ["doctor", "nurse", "billing_executive", "technician", "admin"],
    "clinical": ["doctor", "admin"],
    "nursing": ["nurse", "doctor", "admin"],
    "billing": ["billing_executive", "admin"],
    "equipment": ["technician", "admin"],
}

# Roles allowed to use SQL RAG (analytical questions over mediassist.db)
SQL_RAG_ROLES = {"billing_executive", "admin"}

# Demo accounts: username -> (password, role, display name)
DEMO_USERS: dict[str, tuple[str, str, str]] = {
    "dr.mehta": ("doctor123", "doctor", "Dr. Anil Mehta"),
    "nurse.priya": ("nurse123", "nurse", "Priya Nair"),
    "billing.ravi": ("billing123", "billing_executive", "Ravi Kumar"),
    "tech.anand": ("tech123", "technician", "Anand Joshi"),
    "admin.sys": ("admin123", "admin", "System Administrator"),
}

ROLE_LABELS = {
    "doctor": "🩺 Doctor",
    "nurse": "💉 Nurse",
    "billing_executive": "🧾 Billing Executive",
    "technician": "🔧 Technician",
    "admin": "🛡️ Admin",
}
