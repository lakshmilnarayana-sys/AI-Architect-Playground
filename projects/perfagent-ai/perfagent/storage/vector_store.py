from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Callable


def chunk_text(text: str, *, chunk_size: int = 1200, overlap: int = 120) -> list[str]:
    text = " ".join(text.split())
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        chunks.append(text[start : start + chunk_size])
        start += max(1, chunk_size - overlap)
    return chunks


def deterministic_embedding(text: str, *, dimensions: int = 32) -> list[float]:
    values = [0.0] * dimensions
    for token in text.lower().split():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = digest[0] % dimensions
        values[index] += 1.0
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [round(value / norm, 6) for value in values]


def build_run_narrative_chunks(
    *,
    report_text: str | None = None,
    summary: dict[str, Any] | None = None,
    logs: dict[str, str] | list[str] | None = None,
    chunk_size: int = 1200,
    overlap: int = 120,
) -> dict[str, list[str]]:
    chunks: dict[str, list[str]] = {}
    if report_text:
        chunks["report"] = chunk_text(report_text, chunk_size=chunk_size, overlap=overlap)
    if summary:
        summary_text = json.dumps(summary, sort_keys=True, default=str)
        chunks["summary"] = chunk_text(summary_text, chunk_size=chunk_size, overlap=overlap)
    if isinstance(logs, dict):
        for name, text in logs.items():
            log_chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
            if log_chunks:
                chunks[f"log:{name}"] = log_chunks
    else:
        for index, text in enumerate(logs or []):
            log_chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
            if log_chunks:
                chunks[f"log:{index}"] = log_chunks
    return chunks


def index_run_narratives(
    vector_store: Any,
    *,
    run_id: str,
    report_text: str | None = None,
    summary: dict[str, Any] | None = None,
    logs: dict[str, str] | list[str] | None = None,
    model: str = "deterministic-local",
    chunk_size: int = 1200,
    overlap: int = 120,
) -> int:
    total = 0
    chunks_by_type = build_run_narrative_chunks(
        report_text=report_text,
        summary=summary,
        logs=logs,
        chunk_size=chunk_size,
        overlap=overlap,
    )
    for chunk_type, chunks in chunks_by_type.items():
        total += vector_store.upsert_chunks(run_id=run_id, chunk_type=chunk_type, chunks=chunks, model=model)
    return total


class PgVectorStore:
    def __init__(self, dsn: str, *, connect: Callable[..., Any] | None = None) -> None:
        self.dsn = dsn
        self._connect = connect or _load_psycopg_connect()
        self._init_schema()

    def upsert_chunks(self, *, run_id: str, chunk_type: str, chunks: list[str], model: str = "deterministic-local") -> int:
        with self._connect(self.dsn) as conn:
            with conn.cursor() as cursor:
                for index, text in enumerate(chunks):
                    embedding = deterministic_embedding(text)
                    cursor.execute(
                        """
                        INSERT INTO perf_embeddings (run_id, chunk_type, chunk_index, chunk_text, embedding, model)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (run_id, chunk_type, chunk_index) DO UPDATE SET
                          chunk_text = EXCLUDED.chunk_text,
                          embedding = EXCLUDED.embedding,
                          model = EXCLUDED.model
                        """,
                        (run_id, chunk_type, index, text, embedding, model),
                    )
        return len(chunks)

    def similar(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        embedding = deterministic_embedding(query)
        with self._connect(self.dsn) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT run_id, chunk_type, chunk_index, chunk_text, model,
                           embedding <=> %s AS distance
                    FROM perf_embeddings
                    ORDER BY embedding <=> %s
                    LIMIT %s
                    """,
                    (embedding, embedding, limit),
                )
                columns = [column[0] for column in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _init_schema(self) -> None:
        with self._connect(self.dsn) as conn:
            with conn.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS perf_embeddings (
                      run_id TEXT NOT NULL,
                      chunk_type TEXT NOT NULL,
                      chunk_index INTEGER NOT NULL,
                      chunk_text TEXT NOT NULL,
                      embedding vector(32) NOT NULL,
                      model TEXT NOT NULL,
                      created_at TIMESTAMPTZ DEFAULT now(),
                      PRIMARY KEY (run_id, chunk_type, chunk_index)
                    )
                    """
                )


def _load_psycopg_connect() -> Callable[..., Any]:
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("pgvector search requires psycopg and Postgres with pgvector enabled.") from exc
    return psycopg.connect
