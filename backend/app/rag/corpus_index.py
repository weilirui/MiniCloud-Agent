"""Corpus-wide lexical index for production hybrid retrieval.

Why this file exists
--------------------
``HybridRetriever`` needs a :class:`~app.rag.lexical.LexicalIndex` to run its
BM25 branch. In the eval harness that index is built from a small in-memory
corpus, but the production pipeline stores chunks in Qdrant and never keeps a
local copy. Without an adapter the hybrid branch would silently degrade to
dense-only — which is exactly what happened before this module existed.

Design decisions
----------------
* **Rebuild from Qdrant, not incrementally.** Chunk ids are derived with
  :func:`~app.rag.hybrid.hit_id` on *both* sides, so ids can never drift
  between the dense and lexical branch. Incremental ``add()`` would require
  ingest to reproduce the same id derivation — one missed field and the two
  branches stop agreeing.
* **Lazy + dirty flag.** Ingestion and deletion only mark the index dirty; the
  rebuild happens on the next search. A batch upload of 20 files therefore
  costs one scroll, not twenty.
* **Failure is non-fatal.** If Qdrant is unreachable at rebuild time the
  retriever falls back to dense-only. The lexical branch is an enhancement,
  never a new single point of failure.
"""

from __future__ import annotations

from typing import Any, Iterable

from app.rag.hybrid import hit_id
from app.rag.lexical import LexicalIndex
from app.utils.logging import get_logger

logger = get_logger(__name__)


class CorpusLexicalIndex:
    """A :class:`LexicalIndex` kept in sync with whatever sits in the vector store.

    Implements the small surface ``HybridRetriever`` expects — ``size``,
    ``search()`` and ``text_of()`` — so it can be passed directly as the
    ``lexical_index`` argument.
    """

    def __init__(
        self,
        store: Any,
        *,
        max_chunks: int = 20_000,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self._store = store
        self._max_chunks = max_chunks
        self._k1 = k1
        self._b = b
        self._index: LexicalIndex | None = None
        self._dirty = True

    # ------------------------------------------------------------------ state

    @property
    def size(self) -> int:
        """Number of indexed chunks. Zero when the index could not be built."""
        index = self._ensure()
        return index.size if index is not None else 0

    def invalidate(self) -> None:
        """Mark the index stale; it is rebuilt on the next search."""
        self._dirty = True

    # ----------------------------------------------------------------- lookup

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        index = self._ensure()
        if index is None:
            return []
        return index.search(query, top_k=top_k)

    def text_of(self, doc_id: str) -> str:
        index = self._ensure()
        if index is None:
            return ""
        return index.text_of(doc_id)

    # ----------------------------------------------------------------- build

    def _ensure(self) -> LexicalIndex | None:
        if self._index is not None and not self._dirty:
            return self._index
        self._rebuild()
        return self._index

    def _rebuild(self) -> None:
        index = LexicalIndex(k1=self._k1, b=self._b)
        count = 0
        truncated = False

        try:
            chunks: Iterable[dict[str, Any]] = self._store.iter_chunks()
            for chunk in chunks:
                if count >= self._max_chunks:
                    truncated = True
                    break
                text = chunk.get("text") or ""
                chunk_id = hit_id(chunk)
                if not chunk_id or not text:
                    continue
                index.add(chunk_id, text)
                count += 1
        except Exception as exc:  # scroll/search failure must not break recall
            logger.warning("lexical_index_rebuild_failed", error=str(exc))
            self._index = None
            self._dirty = True
            return

        index.build()
        self._index = index
        self._dirty = False
        logger.info("lexical_index_rebuilt", chunks=count, truncated=truncated)
