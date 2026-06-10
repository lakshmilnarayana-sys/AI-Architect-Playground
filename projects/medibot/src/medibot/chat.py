"""The /chat pipeline: route the question, enforce RBAC, answer with citations.

Routing: an LLM classifier decides whether the question is analytical
(numbers over claims / maintenance_tickets -> SQL RAG, permitted roles only)
or a document question (-> hybrid retrieval + rerank + cited answer).
"""

from dataclasses import dataclass, field

from medibot.config import ROLE_COLLECTIONS, SQL_RAG_ROLES
from medibot.llm import complete, get_token_usage, reset_token_usage
from medibot.retrieval import HybridRetriever, RetrievedChunk
from medibot.sql_rag import sql_rag_chain_verbose

ROUTER_SYSTEM = """You are a query router for MediBot. Classify the user's question:

- "sql": analytical/statistical questions about billing claims or equipment
  maintenance tickets that need database aggregation (counts, sums, averages,
  trends, "how many", "total amount", "which has the most", date ranges).
- "docs": everything else — questions answered from documents (clinical
  protocols, drug doses, nursing procedures, billing codes & claim procedures,
  equipment operation/calibration manuals, HR/leave/conduct policies).

Reply with exactly one word: sql or docs."""

ANSWER_SYSTEM = """You are MediBot, the internal assistant for MediAssist Health
Network staff. Answer the user's question using ONLY the provided context
passages. Rules:
- If the context does not contain the answer, say you could not find it in the
  documents you have access to — do not invent medical, billing, or technical facts.
- Be precise with doses, codes, and procedural steps; quote them exactly as written.
- Cite sources inline as [1], [2] matching the numbered passages.
- Keep the answer focused and well formatted (short paragraphs or bullet lists)."""


@dataclass
class ChatResponse:
    answer: str
    sources: list[dict] = field(default_factory=list)
    retrieval_type: str = "hybrid_rag"  # "hybrid_rag" | "sql_rag" | "blocked"
    role: str = ""
    sql: str | None = None
    rerank_scores: list[float] = field(default_factory=list)
    token_usage: dict = field(default_factory=dict)


def _is_analytical(question: str) -> bool:
    verdict = complete(ROUTER_SYSTEM, question, temperature=0.0)
    return verdict.strip().lower().startswith("sql")


def _blocked_message(role: str) -> str:
    allowed = ", ".join(ROLE_COLLECTIONS[role])
    return (
        f"As a **{role.replace('_', ' ')}**, you don't have access to the documents "
        f"that would answer this question. I can only answer questions from the "
        f"**{allowed}** collections. If you believe you need this access, please "
        f"contact the IT administration team."
    )


def _answer_from_chunks(question: str, chunks: list[RetrievedChunk]) -> str:
    context = "\n\n".join(
        f"[{i}] ({c.source_document} — {c.section_title or 'untitled section'})\n{c.text}"
        for i, c in enumerate(chunks, 1)
    )
    return complete(ANSWER_SYSTEM, f"Context passages:\n{context}\n\nQuestion: {question}")


def chat(question: str, role: str, retriever: HybridRetriever) -> ChatResponse:
    reset_token_usage()
    if _is_analytical(question):
        if role not in SQL_RAG_ROLES:
            return ChatResponse(
                answer=(
                    f"Analytical database queries (claims and maintenance statistics) are "
                    f"restricted to billing executives and admins. "
                    + _blocked_message(role)
                ),
                retrieval_type="blocked",
                role=role,
                token_usage=get_token_usage(),
            )
        result = sql_rag_chain_verbose(question)
        return ChatResponse(
            answer=result["answer"],
            sources=[
                {
                    "source_document": "mediassist.db",
                    "section_title": "claims / maintenance_tickets",
                    "collection": "database",
                }
            ],
            retrieval_type="sql_rag",
            role=role,
            sql=result["sql"],
            token_usage=get_token_usage(),
        )

    # Document question: RBAC filter is applied inside Qdrant by the retriever.
    chunks = retriever.search(question, role)
    if not chunks:
        return ChatResponse(
            answer=_blocked_message(role),
            retrieval_type="blocked",
            role=role,
            token_usage=get_token_usage(),
        )

    answer = _answer_from_chunks(question, chunks)
    return ChatResponse(
        answer=answer,
        sources=[
            {
                "source_document": c.source_document,
                "section_title": c.section_title,
                "collection": c.collection,
            }
            for c in chunks
        ],
        retrieval_type="hybrid_rag",
        role=role,
        rerank_scores=[c.rerank_score for c in chunks],
        token_usage=get_token_usage(),
    )
