from perfagent.storage.vector_store import chunk_text, deterministic_embedding


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
