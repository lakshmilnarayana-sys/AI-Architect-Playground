"""Document ingestion: Docling structural parsing + hierarchical chunking.

Parses every PDF / Markdown file under data/<collection>/ with structural
awareness (headings, tables, code blocks preserved), chunks along the
document's natural hierarchy first and token limits second (HybridChunker),
and writes the result to data/processed/chunks.json.

Each chunk record carries:
  - text:        section-heading-contextualised text (what gets embedded)
  - raw_text:    the chunk body without the injected heading context
  - metadata:    source_document, collection, access_roles, section_title,
                 chunk_type

Run once before serving the app:
    python -m medibot.ingest
"""

import json

from docling.document_converter import DocumentConverter
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.types.doc.labels import DocItemLabel

from medibot.config import CHUNKS_PATH, COLLECTION_ROLES, DATA_DIR, DENSE_MODEL

MAX_TOKENS = 512  # token-aware second pass, matched to the embedding model

_LABEL_TO_CHUNK_TYPE = {
    DocItemLabel.TABLE: "table",
    DocItemLabel.CODE: "code",
    DocItemLabel.SECTION_HEADER: "heading",
    DocItemLabel.TITLE: "heading",
}


def _chunk_type(chunk) -> str:
    """Classify a chunk from the labels of the doc items it contains."""
    labels = {item.label for item in chunk.meta.doc_items}
    for label, chunk_type in _LABEL_TO_CHUNK_TYPE.items():
        if label in labels:
            return chunk_type
    return "text"


def _section_title(chunk) -> str:
    """Deepest heading on the chunk's path through the document hierarchy."""
    headings = chunk.meta.headings or []
    return headings[-1] if headings else ""


def ingest() -> list[dict]:
    converter = DocumentConverter()
    chunker = HybridChunker(tokenizer=DENSE_MODEL, max_tokens=MAX_TOKENS, merge_peers=True)

    records: list[dict] = []
    for collection, roles in COLLECTION_ROLES.items():
        source_dir = DATA_DIR / collection
        for path in sorted(source_dir.iterdir()):
            if path.suffix.lower() not in {".pdf", ".md"}:
                continue
            print(f"[ingest] parsing {collection}/{path.name} ...")
            doc = converter.convert(path).document
            for chunk in chunker.chunk(doc):
                # contextualize() prepends the heading path so every embedded
                # chunk carries its parent section as context.
                records.append(
                    {
                        "text": chunker.contextualize(chunk),
                        "raw_text": chunk.text,
                        "metadata": {
                            "source_document": path.name,
                            "collection": collection,
                            "access_roles": roles,
                            "section_title": _section_title(chunk),
                            "chunk_type": _chunk_type(chunk),
                        },
                    }
                )

    CHUNKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHUNKS_PATH.write_text(json.dumps(records, indent=1, ensure_ascii=False))
    print(f"[ingest] wrote {len(records)} chunks -> {CHUNKS_PATH}")
    return records


if __name__ == "__main__":
    ingest()
