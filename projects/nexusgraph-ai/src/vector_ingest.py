from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHROMA_PATH = ROOT / 'vector_store' / 'chroma'
DEFAULT_COLLECTION = 'nexusgraph_ai_knowledge'
VECTOR_DIMENSIONS = 512

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


STOPWORDS = {
    'a', 'an', 'and', 'are', 'as', 'by', 'for', 'from', 'graph', 'id', 'in',
    'is', 'named', 'node', 'of', 'on', 'relationship', 'service', 'services',
    'the', 'to', 'what', 'which', 'who', 'with'
}
TOKEN_ALIASES = {
    'depends': 'depend',
    'dependency': 'depend',
    'dependencies': 'depend',
    'dependent': 'depend',
    'oncall': 'on-call',
    'call': 'on-call',
    'primary': 'current',
    'secondary': 'current',
    'schedules': 'schedule',
    'runbooks': 'runbook',
    'dashboards': 'dashboard',
    'metrics': 'metric',
}


def tokenize(text: str) -> list[str]:
    normalized = []
    for char in text.lower():
        normalized.append(char if char.isalnum() else ' ')
    raw_tokens = ''.join(normalized).split()
    tokens = []
    for token in raw_tokens:
        if token in STOPWORDS or len(token) < 2:
            continue
        token = TOKEN_ALIASES.get(token, token)
        tokens.append(token)
        if token.endswith('s') and len(token) > 3:
            tokens.append(token[:-1])
    return tokens


def stable_embedding(text: str, dimensions: int = VECTOR_DIMENSIONS) -> list[float]:
    values = [0.0] * dimensions
    tokens = tokenize(text)
    for token in tokens:
        digest = hashlib.sha256(token.encode('utf-8')).digest()
        index = int.from_bytes(digest[:4], 'big') % dimensions
        values[index] += 1.0
    # Add adjacent token pairs so relationship phrases like current oncall and playback depend have signal.
    for left, right in zip(tokens, tokens[1:]):
        pair = f'{left}_{right}'
        digest = hashlib.sha256(pair.encode('utf-8')).digest()
        index = int.from_bytes(digest[:4], 'big') % dimensions
        values[index] += 1.5
    norm = sum(v * v for v in values) ** 0.5 or 1.0
    return [v / norm for v in values]


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
    import chromadb

    documents = build_ingestion_documents()
    persist_path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(persist_path))
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={'description': 'nexusgraph-ai vector RAG baseline collection'},
    )

    ids = [doc['id'] for doc in documents]
    collection.add(
        ids=ids,
        documents=[doc['text'] for doc in documents],
        metadatas=[doc['metadata'] for doc in documents],
        embeddings=[stable_embedding(doc['text']) for doc in documents],
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
