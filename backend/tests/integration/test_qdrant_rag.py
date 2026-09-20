"""Integration tests against a real Qdrant.

Embeddings come from the offline ``HashingEmbedder`` so the round-trip costs
nothing and is deterministic - the point here is to prove the Qdrant wiring
(collection, upsert, search, delete) works, not to score the embedding model.
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.rag.hybrid import HybridConfig, HybridRetriever
from app.rag.lexical import LexicalIndex
from app.rag.qdrant_store import QdrantStore
from eval.offline_embedder import HashingEmbedder

pytestmark = pytest.mark.integration

TEST_COLLECTION = "minicloud_kb_test"
EMBED_DIM = 64

CHUNKS = [
    {"text": "RAG 入库时会把文档切成文本块，默认 chunk_size 为 800。", "source": "doc-a", "doc_id": "doc-a"},
    {"text": "检索时用同一个 embedding 模型把 query 转成向量，默认 top_k 为 5。", "source": "doc-a", "doc_id": "doc-a"},
    {"text": "Qdrant 使用余弦相似度做向量检索，集合名是 minicloud_kb。", "source": "doc-b", "doc_id": "doc-b"},
    {"text": "前端使用 React 与 Vite，三栏布局，通过 SSE 消费流式响应。", "source": "doc-c", "doc_id": "doc-c"},
]


@pytest.fixture
def store():
    qdrant = QdrantStore(
        url=settings.qdrant_url,
        collection=TEST_COLLECTION,
        embedding=HashingEmbedder(dim=EMBED_DIM),
    )
    if not qdrant.health_check():
        pytest.skip(f"Qdrant 不可达: {settings.qdrant_url}")
    qdrant.ensure_collection()
    yield qdrant
    try:
        for doc_id in {c["doc_id"] for c in CHUNKS}:
            qdrant.delete_by_doc_id(doc_id)
    except Exception:
        pass


async def test_qdrant_health_check(store):
    assert store.health_check() is True


async def test_upsert_returns_point_ids(store):
    ids = await store.upsert_points(CHUNKS)
    assert len(ids) == len(CHUNKS)
    assert len(set(ids)) == len(ids)


async def test_search_returns_ranked_hits(store):
    await store.upsert_points(CHUNKS)
    hits = await store.search("RAG 检索的 top_k 是多少", top_k=2, score_threshold=-1.0)

    assert len(hits) == 2
    assert hits[0]["score"] >= hits[1]["score"]
    assert all("text" in h and "source" in h for h in hits)


async def test_search_respects_top_k(store):
    await store.upsert_points(CHUNKS)
    hits = await store.search("向量检索", top_k=1, score_threshold=-1.0)
    assert len(hits) == 1


async def test_delete_by_doc_id_removes_only_that_doc(store):
    await store.upsert_points(CHUNKS)
    store.delete_by_doc_id("doc-c")

    hits = await store.search("前端 SSE 流式响应", top_k=10, score_threshold=-1.0)
    assert all(h["source"] != "doc-c" for h in hits)


async def test_count_grows_after_upsert(store):
    before = store.count()
    await store.upsert_points(CHUNKS)
    assert store.count() >= before


async def test_hybrid_retriever_runs_over_real_qdrant(store):
    await store.upsert_points(CHUNKS)

    index = LexicalIndex()
    for i, chunk in enumerate(CHUNKS):
        index.add(f"{chunk['doc_id']}::{i}", chunk["text"])
    index.build()

    retriever = HybridRetriever(
        vector_search=lambda query, top_k=5, **kw: store.search(query, top_k=top_k, score_threshold=-1.0),
        lexical_index=index,
        config=HybridConfig(enable_mmr=True),
    )
    hits = await retriever.retrieve("Qdrant 余弦相似度检索", top_k=3)

    assert 1 <= len(hits) <= 3
    assert all("vector_score" in h and "lexical_score" in h for h in hits)
    assert any("余弦" in h["text"] for h in hits)
