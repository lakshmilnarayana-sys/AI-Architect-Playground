"""Qdrant hybrid index: dense + BM25 sparse vectors stored side by side.

Both vector types are written at index time into a single collection so a
single Qdrant query can search them together (server-side fusion), with the
RBAC metadata filter applied inside the database.
"""

import json

from fastembed import SparseTextEmbedding, TextEmbedding
from qdrant_client import QdrantClient, models

from medibot.config import (
    CHUNKS_PATH,
    COLLECTION_NAME,
    DENSE_MODEL,
    QDRANT_PATH,
    SPARSE_MODEL,
)

BATCH = 32


def get_client() -> QdrantClient:
    """Embedded (local-path) Qdrant — no server process needed."""
    QDRANT_PATH.mkdir(parents=True, exist_ok=True)
    return QdrantClient(path=str(QDRANT_PATH))


def load_chunks() -> list[dict]:
    return json.loads(CHUNKS_PATH.read_text())


def build_index(client: QdrantClient | None = None, force: bool = False) -> QdrantClient:
    client = client or get_client()
    chunks = load_chunks()

    if client.collection_exists(COLLECTION_NAME):
        if not force and client.count(COLLECTION_NAME).count == len(chunks):
            return client  # already indexed
        client.delete_collection(COLLECTION_NAME)

    dense_model = TextEmbedding(DENSE_MODEL)
    sparse_model = SparseTextEmbedding(SPARSE_MODEL)

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            "dense": models.VectorParams(size=384, distance=models.Distance.COSINE)
        },
        sparse_vectors_config={
            "bm25": models.SparseVectorParams(modifier=models.Modifier.IDF)
        },
    )

    texts = [c["text"] for c in chunks]
    point_id = 0
    for start in range(0, len(chunks), BATCH):
        batch = chunks[start : start + BATCH]
        batch_texts = texts[start : start + BATCH]
        dense_vecs = list(dense_model.embed(batch_texts))
        sparse_vecs = list(sparse_model.embed(batch_texts))
        points = []
        for chunk, dv, sv in zip(batch, dense_vecs, sparse_vecs):
            points.append(
                models.PointStruct(
                    id=point_id,
                    vector={
                        "dense": dv.tolist(),
                        "bm25": models.SparseVector(
                            indices=sv.indices.tolist(), values=sv.values.tolist()
                        ),
                    },
                    payload={"text": chunk["text"], **chunk["metadata"]},
                )
            )
            point_id += 1
        client.upsert(COLLECTION_NAME, points)

    print(f"[index] indexed {point_id} chunks into '{COLLECTION_NAME}'")
    return client


if __name__ == "__main__":
    build_index(force=True)
