"""Hybrid retrieval with RBAC enforcement + cross-encoder reranking.

Security model: every Qdrant query leg (dense and BM25) carries a
`must access_roles == <role>` payload filter, so chunks outside the user's
permitted collections are excluded *inside the vector database* — they never
reach the application layer, the reranker, or the LLM.
"""

from dataclasses import dataclass

from fastembed import SparseTextEmbedding, TextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder
from qdrant_client import QdrantClient, models

from medibot.config import (
    CANDIDATES_PER_LEG,
    COLLECTION_NAME,
    DENSE_MODEL,
    RERANK_MODEL,
    RERANK_TOP_K,
    SPARSE_MODEL,
)


@dataclass
class RetrievedChunk:
    text: str
    source_document: str
    section_title: str
    collection: str
    chunk_type: str
    hybrid_score: float
    rerank_score: float | None = None


class HybridRetriever:
    def __init__(self, client: QdrantClient):
        self.client = client
        self.dense_model = TextEmbedding(DENSE_MODEL)
        self.sparse_model = SparseTextEmbedding(SPARSE_MODEL)
        self.reranker = TextCrossEncoder(RERANK_MODEL)

    def _rbac_filter(self, role: str) -> models.Filter:
        return models.Filter(
            must=[models.FieldCondition(key="access_roles", match=models.MatchValue(value=role))]
        )

    def search(
        self,
        query: str,
        role: str,
        candidates: int = CANDIDATES_PER_LEG,
        top_k: int = RERANK_TOP_K,
    ) -> list[RetrievedChunk]:
        """One Qdrant query: dense + BM25 prefetch legs fused with RRF,
        RBAC-filtered server-side, then cross-encoder reranked to top_k."""
        dense_vec = next(iter(self.dense_model.embed([query]))).tolist()
        sparse_raw = next(iter(self.sparse_model.embed([query])))
        sparse_vec = models.SparseVector(
            indices=sparse_raw.indices.tolist(), values=sparse_raw.values.tolist()
        )
        rbac = self._rbac_filter(role)

        result = self.client.query_points(
            collection_name=COLLECTION_NAME,
            prefetch=[
                models.Prefetch(query=dense_vec, using="dense", filter=rbac, limit=candidates),
                models.Prefetch(query=sparse_vec, using="bm25", filter=rbac, limit=candidates),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            query_filter=rbac,
            limit=candidates,
            with_payload=True,
        )

        chunks = [
            RetrievedChunk(
                text=p.payload["text"],
                source_document=p.payload["source_document"],
                section_title=p.payload["section_title"],
                collection=p.payload["collection"],
                chunk_type=p.payload["chunk_type"],
                hybrid_score=p.score,
            )
            for p in result.points
        ]
        if not chunks:
            return []

        scores = list(self.reranker.rerank(query, [c.text for c in chunks]))
        for chunk, score in zip(chunks, scores):
            chunk.rerank_score = float(score)
        chunks.sort(key=lambda c: c.rerank_score, reverse=True)
        return chunks[:top_k]
