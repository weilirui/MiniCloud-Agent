"""Qdrant-backed vector store for evaluation (real-service backend)."""

from __future__ import annotations

from typing import Any

from qdrant_client.http import models as qmodels

from app.rag.qdrant_store import QdrantStore


class QdrantEvalStore:
    """Wraps the production ``QdrantStore`` into the eval ``VectorStore`` shape.

    Chunk ids are carried inside the point payload (``metadata.chunk_id``)
    because ``QdrantStore`` mints its own point UUIDs.
    """

    def __init__(
        self,
        collection: str = "minicloud_kb_eval",
        url: str | None = None,
        embedding: Any | None = None,
    ) -> None:
        self.collection = collection
        self.store = QdrantStore(collection=collection, url=url, embedding=embedding)

    def ensure_collection(self) -> None:
        self.store.ensure_collection()

    async def add(self, chunks: list[dict[str, Any]]) -> None:
        self.ensure_collection()
        payload = [
            {
                "text": c["text"],
                "source": c.get("source", ""),
                "metadata": {**c.get("metadata", {}), "chunk_id": c["id"]},
            }
            for c in chunks
        ]
        await self.store.upsert_points(payload)

    async def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        hits = await self.store.search(query, top_k=top_k, score_threshold=-1.0)
        return [
            {
                "id": h.get("metadata", {}).get("chunk_id", ""),
                "text": h.get("text", ""),
                "source": h.get("source", ""),
                "score": float(h.get("score", 0.0)),
                "metadata": h.get("metadata", {}),
            }
            for h in hits
        ]

    async def clear(self) -> None:
        """Drop and recreate the evaluation collection."""
        client = self.store._client
        try:
            client.delete_collection(self.collection)
        except Exception:
            pass
        dim = getattr(self.store.embedding, "dim", 1536)
        client.create_collection(
            collection_name=self.collection,
            vectors_config=qmodels.VectorParams(
                size=dim, distance=qmodels.Distance.COSINE
            ),
        )
