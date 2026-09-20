"""Wiring tests for the production hybrid-retrieval path.

These exist because ``HybridRetriever`` was, for a long time, reachable only
from the eval harness: ``Retriever.retrieve()`` called ``QdrantStore.search()``
directly, so every number in the eval report described a pipeline the product
never ran. The tests below pin the connection itself — the lexical branch has
to affect what the production ``Retriever`` returns.
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.rag.corpus_index import CorpusLexicalIndex
from app.rag.retriever import Retriever

CHUNKS = [
    {
        "text": "向量检索采用余弦相似度，在 Qdrant 中做近似最近邻搜索。",
        "source": "rag.md",
        "doc_id": "d1",
        "chunk_index": 0,
    },
    {
        "text": "文档分块按 token 数切分并保留重叠，避免语义被切断。",
        "source": "rag.md",
        "doc_id": "d1",
        "chunk_index": 1,
    },
    {
        "text": "熔断器有三种状态：CLOSED、OPEN、HALF_OPEN，连续失败后快速失败。",
        "source": "retry.md",
        "doc_id": "d2",
        "chunk_index": 0,
    },
]


class FakeStore:
    """Minimal QdrantStore stand-in.

    The dense branch is deliberately *wrong* on purpose: it never returns the
    chunk about circuit breakers. That is the whole point — if the lexical
    branch is wired up, the hybrid result must still surface it.
    """

    def __init__(self, chunks=None, *, scroll_error: Exception | None = None):
        self.chunks = list(chunks or CHUNKS)
        self.scroll_error = scroll_error
        self.search_calls: list[dict] = []
        self.scroll_calls = 0

    async def search(self, query, top_k=5, score_threshold=0.5, filters=None):
        self.search_calls.append({"query": query, "top_k": top_k})
        # Dense branch: only the two chunks from d1, ordered as stored.
        return [
            {
                "text": c["text"],
                "source": c["source"],
                "doc_id": c["doc_id"],
                "chunk_index": c["chunk_index"],
                "score": 0.9 - 0.1 * i,
                "metadata": {},
            }
            for i, c in enumerate(self.chunks[:2])
        ][:top_k]

    def iter_chunks(self, batch_size: int = 256):
        self.scroll_calls += 1
        if self.scroll_error is not None:
            raise self.scroll_error
        yield from self.chunks


# --------------------------------------------------------------- corpus index


def test_corpus_index_rebuilds_from_store_on_first_use():
    store = FakeStore()
    index = CorpusLexicalIndex(store)

    assert index.size == 3
    assert store.scroll_calls == 1

    # Second access is cached: no extra scroll.
    assert index.size == 3
    assert store.scroll_calls == 1


def test_corpus_index_chunk_ids_match_hybrid_hit_ids():
    """Both branches must key chunks identically or fusion silently no-ops."""
    store = FakeStore()
    index = CorpusLexicalIndex(store)

    ids = {doc_id for doc_id, _ in index.search("熔断", top_k=10)}
    assert "d2#0" in ids


def test_corpus_index_invalidate_forces_rebuild():
    store = FakeStore()
    index = CorpusLexicalIndex(store)

    index.search("熔断")
    assert store.scroll_calls == 1

    index.invalidate()
    index.search("熔断")
    assert store.scroll_calls == 2


def test_corpus_index_picks_up_chunks_added_after_invalidation():
    store = FakeStore()
    index = CorpusLexicalIndex(store)
    assert index.size == 3

    store.chunks.append(
        {"text": "新增文档：成本计量按模型计价。", "source": "cost.md", "doc_id": "d3", "chunk_index": 0}
    )
    index.invalidate()

    assert index.size == 4
    assert "d3#0" in {doc_id for doc_id, _ in index.search("成本计量", top_k=10)}


def test_corpus_index_degrades_quietly_when_scroll_fails():
    store = FakeStore(scroll_error=RuntimeError("qdrant down"))
    index = CorpusLexicalIndex(store)

    assert index.size == 0
    assert index.search("熔断") == []
    assert index.text_of("d2#0") == ""


def test_corpus_index_respects_max_chunks():
    store = FakeStore()
    index = CorpusLexicalIndex(store, max_chunks=2)

    assert index.size == 2


# ------------------------------------------------------------------ retriever


@pytest.mark.asyncio
async def test_retriever_uses_lexical_branch_when_hybrid_enabled(monkeypatch):
    monkeypatch.setattr(settings, "rag_hybrid_enabled", True)
    store = FakeStore()
    retriever = Retriever(store=store)

    hits = await retriever.retrieve("熔断器状态机", top_k=3)
    texts = [h["text"] for h in hits]

    # The dense branch alone cannot return this chunk — it only serves d1.
    assert any("熔断器" in t for t in texts), texts


@pytest.mark.asyncio
async def test_retriever_returns_dense_only_when_hybrid_disabled(monkeypatch):
    monkeypatch.setattr(settings, "rag_hybrid_enabled", False)
    store = FakeStore()
    retriever = Retriever(store=store)

    assert retriever.hybrid is None

    hits = await retriever.retrieve("熔断器状态机", top_k=3)
    texts = [h["text"] for h in hits]

    assert not any("熔断器" in t for t in texts), texts
    assert len(store.search_calls) == 1


@pytest.mark.asyncio
async def test_retriever_falls_back_to_dense_when_hybrid_raises(monkeypatch):
    monkeypatch.setattr(settings, "rag_hybrid_enabled", True)
    store = FakeStore()

    async def exploding_search(query, top_k=5, score_threshold=0.5, filters=None):
        raise RuntimeError("dense branch exploded")

    store.search = exploding_search  # type: ignore[method-assign]
    retriever = Retriever(store=store)

    hits = await retriever.retrieve("anything", top_k=3)

    # Hybrid caught the dense failure and returned an empty lexical-only set;
    # it must not propagate the exception to the caller.
    assert isinstance(hits, list)


@pytest.mark.asyncio
async def test_retriever_rebuilds_index_after_invalidation(monkeypatch):
    monkeypatch.setattr(settings, "rag_hybrid_enabled", True)
    store = FakeStore()
    retriever = Retriever(store=store)

    await retriever.retrieve("熔断", top_k=3)
    scrolls_after_first = store.scroll_calls

    store.chunks.append(
        {"text": "反馈闭环：评分低于四星自动标记为坏例。", "source": "fb.md", "doc_id": "d4", "chunk_index": 0}
    )
    retriever.lexical.invalidate()

    hits = await retriever.retrieve("反馈闭环", top_k=5)
    assert store.scroll_calls == scrolls_after_first + 1
    assert any("坏例" in h["text"] for h in hits)


@pytest.mark.asyncio
async def test_retriever_dense_only_when_corpus_index_unusable(monkeypatch):
    """Qdrant unreachable at rebuild time must not make retrieval unavailable."""
    monkeypatch.setattr(settings, "rag_hybrid_enabled", True)
    store = FakeStore(scroll_error=RuntimeError("qdrant down"))
    retriever = Retriever(store=store)

    hits = await retriever.retrieve("熔断器状态机", top_k=3)

    assert hits  # dense branch still answered
    assert len(store.search_calls) >= 1
