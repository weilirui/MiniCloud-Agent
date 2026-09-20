"""Retriever interface: dense-only or hybrid (dense + BM25 + MMR)."""

from __future__ import annotations

from app.config import settings
from app.rag.corpus_index import CorpusLexicalIndex
from app.rag.hybrid import HybridConfig, HybridRetriever
from app.rag.qdrant_store import QdrantStore, get_qdrant_store
from app.utils.logging import get_logger

logger = get_logger(__name__)


class Retriever:
    """High-level retriever wrapping QdrantStore.

    When ``settings.rag_hybrid_enabled`` is on, queries go through
    :class:`HybridRetriever`: dense + BM25 fusion followed by MMR
    re-ranking. Any failure in the hybrid path falls back to the plain dense
    search so retrieval never becomes less available than it was before.
    """

    def __init__(
        self,
        store: QdrantStore | None = None,
        lexical: CorpusLexicalIndex | None = None,
        *,
        hybrid: bool | None = None,
    ):
        self.store = store or get_qdrant_store()

        enabled = settings.rag_hybrid_enabled if hybrid is None else hybrid
        self.lexical: CorpusLexicalIndex | None = lexical
        if self.lexical is None and enabled:
            self.lexical = CorpusLexicalIndex(
                self.store, max_chunks=settings.rag_lexical_max_chunks
            )

        self.hybrid: HybridRetriever | None = None
        if self.lexical is not None:
            self.hybrid = HybridRetriever(
                vector_search=self.store.search,
                lexical_index=self.lexical,
                config=HybridConfig(
                    vector_weight=settings.rag_vector_weight,
                    lexical_weight=settings.rag_lexical_weight,
                    fusion=settings.rag_hybrid_fusion,
                    enable_mmr=settings.rag_mmr_enabled,
                    mmr_lambda=settings.rag_mmr_lambda,
                ),
            )

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.5,
        filters: dict | None = None,
    ) -> list[dict]:
        """Retrieve top-k relevant chunks."""
        if self.hybrid is None:
            return await self.store.search(
                query=query,
                top_k=top_k,
                score_threshold=score_threshold,
                filters=filters,
            )

        try:
            return await self.hybrid.retrieve(
                query,
                top_k=top_k,
                score_threshold=score_threshold,
                filters=filters,
            )
        except Exception as exc:
            logger.warning("hybrid_retrieve_failed_fallback_dense", error=str(exc))
            return await self.store.search(
                query=query,
                top_k=top_k,
                score_threshold=score_threshold,
                filters=filters,
            )


_retriever: Retriever | None = None


def get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        _retriever = Retriever()
    return _retriever


def invalidate_lexical_index() -> None:
    """Drop the stale lexical index after the corpus changed.

    Called by ingestion and document deletion. Safe to call before the
    retriever singleton exists — the index is rebuilt lazily anyway.
    """
    if _retriever is not None and _retriever.lexical is not None:
        _retriever.lexical.invalidate()
