"""Unit tests for BM25, score fusion, MMR and the hybrid retriever."""

from __future__ import annotations

from typing import Any

import pytest

from app.rag.hybrid import (
    Candidate,
    HybridConfig,
    HybridRetriever,
    fuse_candidates,
    hit_id,
    jaccard,
    mmr_select,
    normalize,
    rrf_fuse,
)
from app.rag.lexical import BM25, LexicalIndex, tokenize


# --------------------------------------------------------------------------
# tokenization / BM25
# --------------------------------------------------------------------------

def test_tokenize_splits_latin_words():
    assert "rag" in tokenize("RAG pipeline rocks")


def test_tokenize_produces_cjk_unigrams_and_bigrams():
    tokens = tokenize("上下文压缩")
    assert "上" in tokens
    assert "上下" in tokens


def test_bm25_ranks_keyword_document_first():
    docs = [
        "RAG 流水线分为入库与检索两段",
        "前端使用 React 与 Vite 构建",
        "数据库迁移由 Alembic 管理",
    ]
    bm25 = BM25().fit(docs)
    hits = bm25.top_k("Alembic 迁移", k=1)
    assert hits[0][0] == 2


def test_bm25_empty_corpus_returns_nothing():
    assert BM25().fit([]).scores("anything") == []


def test_bm25_ignores_unmatched_query():
    bm25 = BM25().fit(["只有这些内容"])
    assert all(score == 0.0 for score in bm25.scores("完全无关的另一个词"))


def test_lexical_index_maps_ids_to_scores(tmp_path):
    index = LexicalIndex()
    index.add("c1", "Qdrant 向量数据库")
    index.add("c2", "PostgreSQL 关系数据库")
    index.build()

    hits = index.search("Qdrant", top_k=2)
    assert hits[0][0] == "c1"
    assert index.text_of("c1") == "Qdrant 向量数据库"


# --------------------------------------------------------------------------
# fusion helpers
# --------------------------------------------------------------------------

def test_normalize_maps_to_unit_range():
    assert normalize([1.0, 2.0, 3.0]) == [0.0, 0.5, 1.0]


def test_normalize_flat_scores():
    assert normalize([2.0, 2.0, 2.0]) == [1.0, 1.0, 1.0]
    assert normalize([]) == []


def test_rrf_fuse_rewards_agreement():
    fused = rrf_fuse([["a", "b"], ["b", "c"]])
    assert fused["b"] > fused["a"]
    assert fused["b"] > fused["c"]


def test_jaccard_similarity():
    assert jaccard({"a", "b"}, {"a", "b"}) == 1.0
    assert jaccard({"a"}, {"b"}) == 0.0
    assert jaccard(set(), {"a"}) == 0.0


def test_fuse_candidates_merges_both_branches():
    vector_hits = [
        {"id": "c1", "text": "向量命中一", "score": 0.9, "source": "doc1"},
        {"id": "c2", "text": "向量命中二", "score": 0.6, "source": "doc1"},
    ]
    lexical_hits = [("c2", 9.0), ("c3", 1.0)]

    merged = fuse_candidates(vector_hits, lexical_hits, HybridConfig())
    ids = [c.id for c in merged]
    assert set(ids) == {"c1", "c2", "c3"}

    # c2 is last in the dense branch but top of the lexical branch, so fusion
    # lifts it above c3, which is last in the only branch it appears in.
    assert ids.index("c2") < ids.index("c3")
    # the dense-only winner still leads on the weighted mix
    assert ids[0] == "c1"


def test_fuse_candidates_records_branch_scores():
    vector_hits = [{"id": "c1", "text": "x", "score": 0.9}]
    lexical_hits = [("c2", 5.0)]

    merged = {c.id: c for c in fuse_candidates(vector_hits, lexical_hits, HybridConfig())}
    assert merged["c1"].vector_score == 1.0 and merged["c1"].lexical_score == 0.0
    assert merged["c2"].vector_score == 0.0 and merged["c2"].lexical_score == 1.0


def test_fuse_last_in_both_branches_scores_zero():
    """Min-max normalization makes the tail of each branch 0 - intended behaviour."""
    vector_hits = [
        {"id": "c1", "text": "x", "score": 0.9},
        {"id": "c2", "text": "y", "score": 0.4},
    ]
    lexical_hits = [("c3", 8.0), ("c2", 3.0)]

    merged = {c.id: c for c in fuse_candidates(vector_hits, lexical_hits, HybridConfig())}
    assert merged["c2"].fused_score == 0.0
    assert merged["c1"].fused_score > merged["c3"].fused_score


def test_fuse_candidates_supports_rrf():
    vector_hits = [{"id": "c1", "text": "x", "score": 0.9}]
    lexical_hits = [("c2", 5.0)]
    merged = fuse_candidates(vector_hits, lexical_hits, HybridConfig(fusion="rrf"))
    assert {c.id for c in merged} == {"c1", "c2"}


# --------------------------------------------------------------------------
# chunk id resolution
# --------------------------------------------------------------------------

def test_hit_id_prefers_explicit_id():
    assert hit_id({"id": "c1", "doc_id": "d1"}) == "c1"


def test_hit_id_falls_back_to_doc_id_and_chunk_index():
    """Production ``QdrantStore.search`` emits no ``id``, only doc_id + chunk_index."""
    assert hit_id({"doc_id": "d1", "chunk_index": 3}) == "d1#3"


def test_hit_id_digests_text_when_no_identifier_exists():
    hit = {"text": "没有任何标识的片段", "score": 0.5}
    resolved = hit_id(hit)
    assert resolved.startswith("text:")
    # stable across calls, so fusion keys stay consistent within a process
    assert resolved == hit_id(hit)


def test_hit_id_returns_empty_for_unidentifiable_hit():
    assert hit_id({"score": 0.5}) == ""


def test_fuse_candidates_handles_qdrant_shaped_hits():
    """Regression: hard-coding ``hit["id"]`` raised KeyError against the real store."""
    vector_hits = [
        {"doc_id": "doc-a", "chunk_index": 0, "text": "混合检索融合", "score": 0.9, "source": "a.md"},
        {"doc_id": "doc-b", "chunk_index": 1, "text": "熔断与重试", "score": 0.7, "source": "b.md"},
    ]
    lexical_hits = [("doc-b#1", 6.0), ("doc-c#0", 1.0)]

    merged = {c.id: c for c in fuse_candidates(vector_hits, lexical_hits, HybridConfig())}
    assert set(merged) == {"doc-a#0", "doc-b#1", "doc-c#0"}
    # doc_id / chunk_index survive into metadata for citation
    assert merged["doc-a#0"].metadata["doc_id"] == "doc-a"
    assert merged["doc-a#0"].metadata["chunk_index"] == 0


def test_fuse_candidates_drops_unidentifiable_hits():
    """A hit with neither id nor text cannot be keyed, so it must not collapse
    into one shared "" bucket with every other anonymous hit."""
    vector_hits = [{"score": 0.9}, {"score": 0.8}]
    merged = fuse_candidates(vector_hits, [], HybridConfig())
    assert merged == []


def test_mmr_select_removes_near_duplicates():
    base = "上下文压缩会在超出预算时触发摘要"
    items = [
        Candidate(id="a", text=base, fused_score=0.9),
        Candidate(id="b", text=base + "补充说明", fused_score=0.88),
        Candidate(id="c", text="前端使用 React 三栏布局", fused_score=0.5),
    ]
    picked = mmr_select(items, top_k=2, lambda_=0.5)
    assert [c.id for c in picked] == ["a", "c"]


def test_mmr_select_returns_all_when_fewer_than_k():
    items = [Candidate(id="a", text="x", fused_score=1.0)]
    assert len(mmr_select(items, top_k=5)) == 1


# --------------------------------------------------------------------------
# hybrid retriever
# --------------------------------------------------------------------------

class FakeVectorSearch:
    """Returns a fixed set of dense hits; can be told to fail."""

    def __init__(self, hits: list[dict[str, Any]], fail: bool = False) -> None:
        self.hits = hits
        self.fail = fail
        self.queries: list[str] = []

    async def __call__(self, query: str, top_k: int = 5, **_: Any) -> list[dict[str, Any]]:
        self.queries.append(query)
        if self.fail:
            raise ConnectionError("qdrant down")
        return self.hits[:top_k]


async def test_hybrid_degrades_to_dense_only_without_lexical_index():
    searcher = FakeVectorSearch([{"id": "c1", "text": "命中", "score": 0.9, "source": "d"}])
    retriever = HybridRetriever(vector_search=searcher, lexical_index=None)

    hits = await retriever.retrieve("查询", top_k=5)
    assert [h["id"] for h in hits] == ["c1"]
    assert hits[0]["lexical_score"] == 0.0


async def test_hybrid_survives_dense_branch_failure():
    index = LexicalIndex()
    index.add("c9", "关键词命中")
    index.build()

    retriever = HybridRetriever(
        vector_search=FakeVectorSearch([], fail=True), lexical_index=index
    )
    hits = await retriever.retrieve("关键词", top_k=3)
    assert [h["id"] for h in hits] == ["c9"]


async def test_hybrid_combines_dense_and_lexical():
    index = LexicalIndex()
    index.add("lex1", "BM25 关键词检索")
    index.build()

    dense = [{"id": "vec1", "text": "向量召回结果", "score": 0.95, "source": "d"}]
    retriever = HybridRetriever(vector_search=FakeVectorSearch(dense), lexical_index=index)

    hits = await retriever.retrieve("关键词", top_k=5)
    ids = [h["id"] for h in hits]
    assert "vec1" in ids and "lex1" in ids
    assert all("vector_score" in h and "lexical_score" in h for h in hits)


async def test_hybrid_respects_top_k():
    index = LexicalIndex()
    for i in range(10):
        index.add(f"c{i}", f"文档片段 {i} 关键词")
    index.build()

    retriever = HybridRetriever(vector_search=FakeVectorSearch([]), lexical_index=index)
    hits = await retriever.retrieve("关键词", top_k=3)
    assert len(hits) == 3


async def test_mmr_can_be_disabled():
    base = "重复内容重复内容"
    index = LexicalIndex()
    index.add("a", base)
    index.add("b", base + "变体")
    index.build()

    dense = [{"id": "a", "text": base, "score": 0.9}]
    with_mmr = HybridRetriever(
        vector_search=FakeVectorSearch(dense),
        lexical_index=index,
        config=HybridConfig(enable_mmr=True, mmr_lambda=0.3),
    )
    without_mmr = HybridRetriever(
        vector_search=FakeVectorSearch(dense),
        lexical_index=index,
        config=HybridConfig(enable_mmr=False),
    )

    assert len(await with_mmr.retrieve("重复内容", top_k=2)) == 2
    assert len(await without_mmr.retrieve("重复内容", top_k=2)) == 2


@pytest.mark.parametrize("fusion", ["weighted", "rrf"])
async def test_both_fusion_modes_return_results(fusion):
    index = LexicalIndex()
    index.add("c1", "混合检索")
    index.build()

    retriever = HybridRetriever(
        vector_search=FakeVectorSearch([{"id": "c2", "text": "向量", "score": 0.8}]),
        lexical_index=index,
        config=HybridConfig(fusion=fusion),
    )
    hits = await retriever.retrieve("混合检索", top_k=2)
    assert len(hits) >= 1
