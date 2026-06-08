from __future__ import annotations

import argparse
import json
from pathlib import Path

from vector_ingest import DEFAULT_CHROMA_PATH, DEFAULT_COLLECTION, stable_embedding


def query_vector_store(
    query: str,
    persist_path: Path = DEFAULT_CHROMA_PATH,
    collection_name: str = DEFAULT_COLLECTION,
    n_results: int = 5,
) -> dict:
    import chromadb

    client = chromadb.PersistentClient(path=str(persist_path))
    collection = client.get_collection(collection_name)
    result = collection.query(
        query_embeddings=[stable_embedding(query)],
        n_results=n_results,
        include=['documents', 'metadatas', 'distances'],
    )
    matches = []
    for idx, doc_id in enumerate(result['ids'][0]):
        matches.append({
            'id': doc_id,
            'distance': result['distances'][0][idx],
            'metadata': result['metadatas'][0][idx],
            'document': result['documents'][0][idx],
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
