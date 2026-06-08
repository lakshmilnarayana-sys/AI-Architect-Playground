# Design Spec: Hybrid Router RAG (LangChain + LangGraph)

**Date:** 2026-06-08
**Topic:** Refactoring custom RAG to LangChain + LangGraph (Project 3: GraphRAG)

## 1. One-Liner
My RAG app helps **technical teams** answer **organizational and architectural questions** from **local team knowledge (YAML/CSV/Markdown)** in a **CLI/Streamlit interface** with high **faithfulness and relationship awareness**.

## 2. Architecture: The Hybrid Router
We will implement a stateful router using **LangGraph** that orchestrates two primary retrieval paths:

### Path A: Vector RAG (ChromaDB)
- **Best for:** Semantic similarity, general descriptions, and unstructured documentation.
- **Implementation:** LangChain `Chroma` vector store with custom `StableEmbeddings`.

### Path B: Graph RAG (Neo4j)
- **Best for:** Relationship queries (e.g., "Who depends on X?", "What decisions affected Y?"), multi-hop traversals.
- **Implementation:** `LangChain-Neo4j` integration using Cypher generation or Graph QA chains.

### The Router (LangGraph)
- **Logic:** A supervisor node (LLM) analyzes the query.
- **Decisions:** 
    - `vector_only`: Simple semantic lookup.
    - `graph_only`: Relationship/entity-specific lookup.
    - `compare`: Executes both paths (required for the Week 2 Comparison Report).

## 3. Tech Stack
- **Orchestration:** LangGraph (Stateful functional graph).
- **Framework:** LangChain (LCEL for chains, standard interfaces for stores).
- **Vector Store:** ChromaDB (Full re-ingestion required for 384-dim semantic embeddings).
- **Graph Store:** Neo4j (Local instance via `NEO4J_URI`).
- **Embeddings:** `HuggingFaceEmbeddings` using `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions).
- **LLM:** Groq (via `LangChain-Groq` and `ChatGroq`) or OpenAI (configured via `.env`).

## 4. Implementation Plan
1. **Setup:** Install `sentence-transformers`, `langchain-huggingface`, and `langchain-groq`.
2. **Re-ingestion:** Update `src/vector_ingest.py` to use `HuggingFaceEmbeddings` and re-populate Chroma.
3. **Retrievers:** Initialize `Chroma` and `Neo4jGraph` as LangChain-compatible objects.
4. **Graph Nodes:**
    - `router_node`: Uses LLM (Groq) to determine the path.
    - `vector_retrieval_node`: Fetches context from Chroma.
    - `graph_retrieval_node`: Fetches context from Neo4j (using Cypher generation).
    - `synthesizer_node`: Generates the final grounded answer.
5. **Comparison Tool:** A dedicated script to run the "10-query comparison" required by the guidelines, outputting a Markdown report.

## 5. Success Criteria
- [ ] Strictly uses LangChain/LangGraph primitives.
- [ ] Maintains the 20+ node graph structure.
- [ ] Successfully routes "relationship" questions to Neo4j.
- [ ] Generates a comparison report for 10 specific queries.
