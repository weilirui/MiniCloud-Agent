"""In-memory vector store: offline default for the evaluation runner."""

from __future__ import annotations

from typing import Any

from eval.offline_embedder import HashingEmbedder
from eval.stores.base import cosine


class InMemoryVectorStore:
    """Brute-force cosine search over an in-memory index."""

    def __init__(self, embedder: HashingEmbedder | None = None) -> None:
        self.embedder = embedder or HashingEmbedder()
        self._chunks: list[dict[str, Any]] = []
        self._vectors: list[list[float]] = []

    async def add(self, chunks: list[dict[str, Any]]) -> None:
        vectors = await self.embedder.embed([c["text"] for c in chunks])
        for chunk, vec in zip(chunks, vectors):
            self._chunks.append(chunk)
            self._vectors.append(vec)

    async def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        if not self._chunks:
            return []
        qvec = await self.embedder.embed_one(query)
        scored = [
            (cosine(qvec, vec), idx) for idx, vec in enumerate(self._vectors)
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "id": self._chunks[idx]["id"],
                "text": self._chunks[idx]["text"],
                "source": self._chunks[idx].get("source", ""),
                "score": float(score),
                "metadata": self._chunks[idx].get("metadata", {}),
            }
            for score, idx in scored[:top_k]
        ]

    async def clear(self) -> None:
        self._chunks.clear()
        self._vectors.clear()

    def __len__(self) -> int:
        return len(self._chunks)
