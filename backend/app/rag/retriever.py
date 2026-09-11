"""Retriever interface."""

from __future__ import annotations

from app.rag.qdrant_store import QdrantStore, get_qdrant_store


class Retriever:
    """High-level retriever wrapping QdrantStore."""

    def __init__(self, store: QdrantStore | None = None):
        self.store = store or get_qdrant_store()

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.5,
        filters: dict | None = None,
    ) -> list[dict]:
        """Retrieve top-k relevant chunks."""
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