from perfagent.storage.vector_store import (
    build_run_narrative_chunks,
    chunk_text,
    deterministic_embedding,
    index_run_narratives,
)


def test_chunk_text_overlaps_long_text():
    chunks = chunk_text(" ".join(["latency"] * 400), chunk_size=80, overlap=10)

    assert len(chunks) > 1
    assert all(chunks)


def test_deterministic_embedding_is_stable_and_normalized():
    first = deterministic_embedding("p95 latency regression database")
    second = deterministic_embedding("p95 latency regression database")

    assert first == second
    assert len(first) == 32
    assert max(first) > 0


def test_build_run_narrative_chunks_splits_report_summary_and_logs():
    chunks = build_run_narrative_chunks(
        report_text="p95 latency regressed during checkout",
        summary={"run_id": "run-1", "release_decision": "WARN"},
        logs={"k6": "WARN request duration exceeded threshold"},
        chunk_size=30,
        overlap=5,
    )

    assert set(chunks) == {"report", "summary", "log:k6"}
    assert all(chunks.values())


def test_index_run_narratives_uses_injected_vector_store_without_postgres():
    class FakeVectorStore:
        def __init__(self):
            self.calls = []

        def upsert_chunks(self, *, run_id, chunk_type, chunks, model):
            self.calls.append(
                {"run_id": run_id, "chunk_type": chunk_type, "chunks": chunks, "model": model}
            )
            return len(chunks)

    store = FakeVectorStore()

    count = index_run_narratives(
        store,
        run_id="run-1",
        report_text="database latency increased under steady load",
        summary={"service_name": "payments-api"},
        logs=["connection pool exhausted"],
    )

    assert count == sum(len(call["chunks"]) for call in store.calls)
    assert {call["chunk_type"] for call in store.calls} == {"report", "summary", "log:0"}
    assert all(call["run_id"] == "run-1" for call in store.calls)
