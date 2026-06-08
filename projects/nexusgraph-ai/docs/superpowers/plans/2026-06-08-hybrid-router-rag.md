# Hybrid Router RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the current custom RAG implementation to use LangChain and LangGraph with a Hybrid Router (Vector + Graph) and semantic embeddings.

**Architecture:** A stateful LangGraph orchestrates routing between ChromaDB (Vector) and Neo4j (Graph). It uses HuggingFace `all-MiniLM-L6-v2` for 384-dim semantic embeddings and Groq for LLM generation/routing.

**Tech Stack:** LangChain, LangGraph, ChromaDB, Neo4j, Groq (LLM), HuggingFace (Embeddings).

---

### Task 1: Setup and Dependency Verification

**Files:**
- Modify: `requirements.txt`
- Create: `.env` (already exists, but verify template)

- [ ] **Step 1: Update requirements.txt**

```text
langchain==1.3.4
langgraph==1.2.4
langchain-openai==1.2.2
langchain-community==0.4.2
langchain-chroma==1.1.0
langchain-neo4j==0.9.0
langchain-huggingface==1.2.2
langchain-groq==1.1.2
sentence-transformers==3.3.1
python-dotenv==1.2.1
neo4j==6.2.0
pandas==2.3.3
chromadb==1.5.9
```

- [ ] **Step 2: Install dependencies in venv**

Run: `source .venv/bin/activate && python3 -m pip install -r requirements.txt`
Expected: Successful installation of all packages.

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: update dependencies for LangChain/LangGraph refactor"
```

---

### Task 2: Implement Semantic Vector Re-ingestion

**Files:**
- Modify: `src/vector_ingest.py`
- Test: `tests/test_vector_ingestion_new.py`

- [ ] **Step 1: Update `src/vector_ingest.py` to use HuggingFaceEmbeddings**

Replace custom `stable_embedding` and Chroma client with LangChain `HuggingFaceEmbeddings` and `Chroma` vector store.

```python
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

def get_embeddings():
    return HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)

def ingest_data():
    embeddings = get_embeddings()
    # ... logic to load documents from CSV/YAML/MD ...
    vectorstore = Chroma.from_documents(
        documents=docs,
        embedding=embeddings,
        persist_directory=str(DEFAULT_CHROMA_PATH),
        collection_name=DEFAULT_COLLECTION
    )
```

- [ ] **Step 2: Run re-ingestion**

Run: `source .venv/bin/activate && python3 src/vector_ingest.py`
Expected: Chroma collection re-created with 384 dimensions.

- [ ] **Step 3: Verify dimensions**

Run: `python3 -c "import chromadb; client = chromadb.PersistentClient(path='vector_store/chroma'); coll = client.get_collection('nexusgraph_ai_knowledge'); print(len(coll.get(include=['embeddings'])['embeddings'][0]))"`
Expected: `384`

- [ ] **Step 4: Commit**

```bash
git add src/vector_ingest.py
git commit -m "feat: switch to semantic HuggingFace embeddings (384-dim)"
```

---

### Task 3: Build the LangGraph Hybrid Router

**Files:**
- Create: `src/hybrid_rag.py`
- Test: `tests/test_hybrid_rag.py`

- [ ] **Step 1: Define the Graph State and Nodes**

Implement the LangGraph structure: `router` -> `vector_node` OR `graph_node` -> `synthesizer`.

```python
import operator
from typing import Annotated, Sequence, TypedDict
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, END

class AgentState(TypedDict):
    query: str
    route: str
    context: Annotated[Sequence[str], operator.add]
    answer: str

def router(state: AgentState):
    # Logic to decide 'vector', 'graph', or 'compare'
    return {"route": "vector"} # Placeholder

# ... Define vector_node, graph_node, synthesizer_node ...

workflow = StateGraph(AgentState)
workflow.add_node("router", router)
# ... add nodes and edges ...
workflow.set_entry_point("router")
```

- [ ] **Step 2: Implement retrieval logic**

- `vector_node`: Uses `vectorstore.as_retriever()`.
- `graph_node`: Uses `GraphCypherQAChain` from `langchain_neo4j`.

- [ ] **Step 3: Run a test query**

Run: `source .venv/bin/activate && python3 src/hybrid_rag.py "Who works on the audit project?"`
Expected: Grounded answer from either vector or graph path.

- [ ] **Step 4: Commit**

```bash
git add src/hybrid_rag.py
git commit -m "feat: implement LangGraph hybrid router"
```

---

### Task 4: Generate Comparison Report

**Files:**
- Create: `src/generate_report.py`
- Create: `evaluation/comparison_results.md`

- [ ] **Step 1: Implement the comparison runner**

Iterate through 10 queries, running both paths and recording the output.

- [ ] **Step 2: Generate the Markdown report**

Expected: `evaluation/comparison_results.md` containing 10 side-by-side results and analysis.

- [ ] **Step 3: Commit**

```bash
git add src/generate_report.py evaluation/comparison_results.md
git commit -m "docs: generate Week 2 RAG comparison report"
```
