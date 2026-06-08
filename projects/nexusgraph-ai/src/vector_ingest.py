from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document
import chromadb

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHROMA_PATH = ROOT / 'vector_store' / 'chroma'
DEFAULT_COLLECTION = 'nexusgraph_ai_knowledge'
VECTOR_DIMENSIONS = 384

SOURCE_GLOBS = [
    'data/*.yaml',
    'docs/*.md',
    'evaluation/*.json',
]


def slug(value: str) -> str:
    cleaned = []
    for char in value.lower():
        if char.isalnum():
            cleaned.append(char)
        else:
            cleaned.append('-')
    return '-'.join(part for part in ''.join(cleaned).split('-') if part)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline='') as handle:
        return list(csv.DictReader(handle))


def graph_node_documents() -> list[dict]:
    docs = []
    for row in read_csv_rows(ROOT / 'graph' / 'nodes.csv'):
        node_id = row['id']
        docs.append({
            'id': f"graph-node-{slug(node_id)}",
            'text': f"{row['label']} node named {row['name']}. Description: {row['description']}. Graph id: {node_id}.",
            'metadata': {
                'source': 'graph/nodes.csv',
                'kind': 'graph_node',
                'label': row['label'],
                'graph_id': node_id,
                'name': row['name'],
            },
        })
    return docs


def graph_edge_documents() -> list[dict]:
    docs = []
    for row in read_csv_rows(ROOT / 'graph' / 'edges.csv'):
        source = row['source']
        relationship = row['relationship']
        target = row['target']
        docs.append({
            'id': f"graph-edge-{slug(source)}-{slug(relationship)}-{slug(target)}",
            'text': f"Graph relationship: {source} {relationship} {target}.",
            'metadata': {
                'source': 'graph/edges.csv',
                'kind': 'graph_edge',
                'relationship': relationship,
                'source_id': source,
                'target_id': target,
            },
        })
    return docs


def source_artifact_documents() -> list[dict]:
    docs = []
    for pattern in SOURCE_GLOBS:
        for path in sorted(ROOT.glob(pattern)):
            relative = path.relative_to(ROOT).as_posix()
            text = path.read_text(errors='replace').strip()
            if not text:
                continue
            docs.append({
                'id': slug(relative),
                'text': f"Source artifact {relative}:\n{text}",
                'metadata': {
                    'source': relative,
                    'kind': 'source_artifact',
                    'file_type': path.suffix.lstrip('.'),
                },
            })
    return docs


def build_ingestion_documents() -> list[dict]:
    return graph_node_documents() + graph_edge_documents() + source_artifact_documents()


def ingest_documents(
    persist_path: Path = DEFAULT_CHROMA_PATH,
    collection_name: str = DEFAULT_COLLECTION,
) -> dict[str, int | str]:
    documents_data = build_ingestion_documents()
    persist_path.mkdir(parents=True, exist_ok=True)

    embeddings = HuggingFaceEmbeddings(model_name='sentence-transformers/all-MiniLM-L6-v2')

    # Clear existing collection
    client = chromadb.PersistentClient(path=str(persist_path))
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass

    documents = [
        Document(page_content=doc['text'], metadata=doc['metadata'])
        for doc in documents_data
    ]
    ids = [doc['id'] for doc in documents_data]

    Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        ids=ids,
        collection_name=collection_name,
        persist_directory=str(persist_path),
    )

    return {
        'collection': collection_name,
        'persist_path': str(persist_path),
        'documents': len(documents),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='Ingest nexusgraph-ai documents into ChromaDB.')
    parser.add_argument('--persist-path', default=str(DEFAULT_CHROMA_PATH))
    parser.add_argument('--collection', default=DEFAULT_COLLECTION)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    documents = build_ingestion_documents()
    if args.dry_run:
        print(json.dumps({'documents': len(documents), 'sample_ids': [doc['id'] for doc in documents[:5]]}, indent=2))
        return

    result = ingest_documents(Path(args.persist_path), args.collection)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
