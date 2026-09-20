"""Qdrant vector store wrapper."""

from __future__ import annotations

import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from qdrant_client.http.exceptions import UnexpectedResponse

from app.config import settings
from app.rag.embeddings import EmbeddingClient, get_embedding_client
from app.utils.logging import get_logger

logger = get_logger(__name__)


class QdrantStore:
    """Async-friendly wrapper around QdrantClient (sync client wrapped)."""

    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        collection: str | None = None,
        embedding: EmbeddingClient | None = None,
    ):
        self.url = url or settings.qdrant_url
        self.api_key = api_key or settings.qdrant_api_key
        self.collection = collection or settings.qdrant_collection
        self.embedding = embedding or get_embedding_client()
        self._client = QdrantClient(url=self.url, api_key=self.api_key)

    def ensure_collection(self) -> None:
        """Create the collection if it doesn't exist."""
        try:
            self._client.get_collection(self.collection)
            logger.info("qdrant_collection_exists", name=self.collection)
        except UnexpectedResponse:
            logger.info("qdrant_creating_collection", name=self.collection, dim=self.embedding.dim)
            self._client.create_collection(
                collection_name=self.collection,
                vectors_config=qmodels.VectorParams(
                    size=self.embedding.dim,
                    distance=qmodels.Distance.COSINE,
                ),
            )

    async def upsert_points(
        self,
        chunks: list[dict],
    ) -> list[str]:
        """Embed and upsert chunks. Returns list of point IDs.

        Each chunk: {"text": str, "source": str, "metadata": dict}
        """
        if not chunks:
            return []

        texts = [c["text"] for c in chunks]
        vectors = await self.embedding.embed(texts)

        points = []
        ids = []
        for chunk, vec in zip(chunks, vectors):
            pid = str(uuid.uuid4())
            ids.append(pid)
            payload = {
                "text": chunk["text"],
                "source": chunk.get("source", ""),
                "doc_id": chunk.get("doc_id"),
                "chunk_index": chunk.get("chunk_index", 0),
                **chunk.get("metadata", {}),
            }
            points.append(qmodels.PointStruct(id=pid, vector=vec, payload=payload))

        self._client.upsert(collection_name=self.collection, points=points)
        logger.info("qdrant_upserted", count=len(points))
        return ids

    async def search(
        self,
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.5,
        filters: dict | None = None,
    ) -> list[dict]:
        """Search by query text. Returns list of {text, source, score, metadata}."""
        vec = await self.embedding.embed_one(query)
        if not vec:
            return []

        qfilter = None
        if filters:
            must = []
            for k, v in filters.items():
                must.append(qmodels.FieldCondition(key=k, match=qmodels.MatchValue(value=v)))
            qfilter = qmodels.Filter(must=must)

        try:
            results = self._client.query_points(
                collection_name=self.collection,
                query=vec,
                limit=top_k,
                score_threshold=score_threshold,
                query_filter=qfilter,
                with_payload=True,
            ).points
        except UnexpectedResponse as e:
            logger.warning("qdrant_search_failed", error=str(e))
            return []

        return [
            {
                "text": r.payload.get("text", ""),
                "source": r.payload.get("source", ""),
                "doc_id": r.payload.get("doc_id"),
                "chunk_index": r.payload.get("chunk_index", 0),
                "score": float(r.score),
                "metadata": {k: v for k, v in (r.payload or {}).items()
                             if k not in ("text", "source", "doc_id", "chunk_index")},
            }
            for r in results
        ]

    def iter_chunks(self, batch_size: int = 256):
        """Yield every stored chunk payload, paging through the collection.

        Used to (re)build the in-memory lexical index. Vectors are skipped;
        only the payload (text + addressing) is needed, which keeps the scroll
        cheap enough to run on startup or after an ingestion.
        """
        offset = None
        while True:
            try:
                points, offset = self._client.scroll(
                    collection_name=self.collection,
                    limit=batch_size,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
            except UnexpectedResponse as exc:
                logger.warning("qdrant_scroll_failed", error=str(exc))
                return

            if not points:
                return

            for point in points:
                payload = point.payload or {}
                yield {
                    "text": payload.get("text", ""),
                    "source": payload.get("source", ""),
                    "doc_id": payload.get("doc_id"),
                    "chunk_index": payload.get("chunk_index", 0),
                    "metadata": {
                        k: v
                        for k, v in payload.items()
                        if k not in ("text", "source", "doc_id", "chunk_index")
                    },
                }

            if offset is None:
                return

    def delete_by_doc_id(self, doc_id: str) -> None:
        """Delete all points belonging to a doc_id."""
        self._client.delete(
            collection_name=self.collection,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(must=[
                    qmodels.FieldCondition(key="doc_id", match=qmodels.MatchValue(value=doc_id))
                ])
            ),
        )

    def count(self) -> int:
        try:
            info = self._client.get_collection(self.collection)
            return info.points_count or 0
        except UnexpectedResponse:
            return 0

    def health_check(self) -> bool:
        try:
            self._client.get_collections()
            return True
        except Exception:
            return False


_qdrant_store: QdrantStore | None = None


def get_qdrant_store() -> QdrantStore:
    global _qdrant_store
    if _qdrant_store is None:
        _qdrant_store = QdrantStore()
    return _qdrant_store