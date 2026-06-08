from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

try:
    from .vector_query import query_vector_store
except ImportError:
    from vector_query import query_vector_store

MAX_CONTEXT_LINES = 6


def clean_document(text: str) -> str:
    text = text.strip().replace('\n', ' ')
    text = re.sub(r'\s+', ' ', text)
    return text


def humanize_graph_statement(text: str) -> str:
    prefix = 'Graph relationship: '
    if text.startswith(prefix):
        statement = text[len(prefix):].rstrip('.')
        return statement
    return clean_document(text)


def synthesize_answer(query: str, matches: list[dict]) -> str:
    if not matches:
        return (
            'Vector RAG answer\n\n'
            f'I could not find relevant vector context for: {query}\n'
        )

    context_lines = []
    sources = []
    for index, match in enumerate(matches[:MAX_CONTEXT_LINES], start=1):
        document = humanize_graph_statement(match.get('document', ''))
        metadata = match.get('metadata') or {}
        source = metadata.get('source', 'unknown')
        distance = match.get('distance')
        score_text = f', distance={distance:.3f}' if isinstance(distance, (float, int)) else ''
        context_lines.append(f'{index}. {document} [{source}{score_text}]')
        sources.append(source)

    unique_sources = []
    for source in sources:
        if source not in unique_sources:
            unique_sources.append(source)

    answer = [
        'Vector RAG answer',
        '',
        f'Question: {query}',
        '',
        'Retrieved context suggests:',
    ]
    answer.extend(context_lines)
    answer.extend([
        '',
        'Sources:',
    ])
    answer.extend(f'- {source}' for source in unique_sources)
    return '\n'.join(answer) + '\n'


def answer_query(query: str, n_results: int = 6, persist_path: Path | None = None) -> str:
    kwargs = {'n_results': n_results}
    if persist_path is not None:
        kwargs['persist_path'] = persist_path
    result = query_vector_store(query, **kwargs)
    return synthesize_answer(query, result['matches'])


def main() -> None:
    parser = argparse.ArgumentParser(description='Answer a question using the local ChromaDB Vector RAG baseline.')
    parser.add_argument('query')
    parser.add_argument('--n-results', type=int, default=6)
    parser.add_argument('--json', action='store_true', help='Emit JSON with query and answer fields.')
    args = parser.parse_args()

    answer = answer_query(args.query, args.n_results)
    if args.json:
        print(json.dumps({'query': args.query, 'answer': answer}, indent=2))
    else:
        print(answer)


if __name__ == '__main__':
    main()
