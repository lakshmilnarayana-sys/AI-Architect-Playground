from __future__ import annotations

import argparse
import json
import threading
from functools import lru_cache
from pathlib import Path

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

from config import DEFAULT_CHROMA_PATH, DEFAULT_COLLECTION, EMBEDDING_MODEL


_VECTOR_STORE_LOCK = threading.Lock()


@lru_cache(maxsize=8)
def get_vector_store(persist_path: str, collection_name: str) -> Chroma:
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    return Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=persist_path,
    )


def query_vector_store(
    query: str,
    persist_path: Path = DEFAULT_CHROMA_PATH,
    collection_name: str = DEFAULT_COLLECTION,
    n_results: int = 5,
) -> dict:
    if not persist_path.exists():
        raise FileNotFoundError(f"Vector store not found at {persist_path}. Did you run src/vector_ingest.py?")

    with _VECTOR_STORE_LOCK:
        vector_store = get_vector_store(str(persist_path), collection_name)
        results = vector_store.similarity_search_with_score(query, k=n_results)

    matches = []
    for doc, score in results:
        matches.append({
            'id': getattr(doc, 'id', 'unknown'),
            'distance': float(score),
            'metadata': doc.metadata,
            'document': doc.page_content,
        })
    return {'query': query, 'matches': matches}


def main() -> None:
    parser = argparse.ArgumentParser(description='Query the nexusgraph-ai ChromaDB vector store.')
    parser.add_argument('query')
    parser.add_argument('--persist-path', default=str(DEFAULT_CHROMA_PATH))
    parser.add_argument('--collection', default=DEFAULT_COLLECTION)
    parser.add_argument('--n-results', type=int, default=5)
    args = parser.parse_args()
    print(json.dumps(query_vector_store(args.query, Path(args.persist_path), args.collection, args.n_results), indent=2))


if __name__ == '__main__':
    main()
