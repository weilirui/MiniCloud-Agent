"""Document ingestion pipeline."""

from __future__ import annotations

from dataclasses import dataclass

from app.rag.chunker import Chunk, chunk_text, load_file_content
from app.rag.qdrant_store import QdrantStore, get_qdrant_store
from app.rag.retriever import invalidate_lexical_index
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class IngestionResult:
    doc_id: str
    chunk_count: int
    point_ids: list[str]


async def ingest_file(
    filename: str,
    content: bytes,
    doc_id: str,
    store: QdrantStore | None = None,
    *,
    chunk_size: int = 800,
    chunk_overlap: int = 100,
) -> IngestionResult:
    """Load → chunk → embed → upsert.

    doc_id: caller-provided (e.g. a UUID stored in KnowledgeDoc).
    """
    store = store or get_qdrant_store()

    text = load_file_content(filename, content)
    if not text.strip():
        raise ValueError("empty document")

    chunks: list[Chunk] = chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    if not chunks:
        raise ValueError("no chunks produced")

    payload_chunks = [
        {
            "text": c.text,
            "source": filename,
            "doc_id": doc_id,
            "chunk_index": c.index,
            "metadata": c.metadata,
        }
        for c in chunks
    ]

    point_ids = await store.upsert_points(payload_chunks)
    # The BM25 branch is built from whatever is in Qdrant, so the corpus just
    # changed underneath it. Marking dirty is enough; the rebuild is lazy.
    invalidate_lexical_index()
    logger.info("ingested", filename=filename, doc_id=doc_id, n_chunks=len(chunks))
    return IngestionResult(doc_id=doc_id, chunk_count=len(chunks), point_ids=point_ids)