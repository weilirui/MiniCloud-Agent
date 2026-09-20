"""Unit tests for the ingestion pipeline and the Retriever wrapper."""

from __future__ import annotations

from typing import Any

import pytest

from app.rag.ingest import ingest_file
from app.rag.retriever import Retriever


class RecordingStore:
    def __init__(self) -> None:
        self.upserted: list[dict[str, Any]] = []
        self._counter = 0
        self.search_results: list[dict[str, Any]] = [
            {"text": "命中片段", "source": "a.md", "score": 0.91, "doc_id": "d1", "chunk_index": 0}
        ]

    async def upsert_points(self, chunks: list[dict]) -> list[str]:
        self.upserted = chunks
        self._counter += len(chunks)
        return [f"point-{i}" for i in range(len(chunks))]

    async def search(self, query: str, top_k: int = 5, **_: Any) -> list[dict[str, Any]]:
        self.last_query = query
        self.last_top_k = top_k
        return self.search_results[:top_k]


async def test_ingest_file_produces_chunks_and_points():
    store = RecordingStore()
    body = "\n\n".join(f"第{i}段内容，用于验证入库切分行为。" for i in range(20))
    result = await ingest_file(
        "notes.md",
        body.encode("utf-8"),
        doc_id="doc-1",
        store=store,
        chunk_size=60,
        chunk_overlap=10,
    )

    assert result.doc_id == "doc-1"
    assert result.chunk_count >= 2
    assert len(result.point_ids) == result.chunk_count
    assert all(p.startswith("point-") for p in result.point_ids)


async def test_ingest_payload_carries_source_and_index():
    store = RecordingStore()
    await ingest_file("doc.md", "内容A。\n\n内容B。".encode("utf-8"), doc_id="doc-2", store=store)

    assert all(chunk["source"] == "doc.md" for chunk in store.upserted)
    assert all(chunk["doc_id"] == "doc-2" for chunk in store.upserted)
    assert [c["chunk_index"] for c in store.upserted] == list(range(len(store.upserted)))


async def test_ingest_rejects_empty_document():
    with pytest.raises(ValueError, match="empty document"):
        await ingest_file("blank.md", b"   \n  ", doc_id="d", store=RecordingStore())


async def test_ingest_rejects_completely_empty_file():
    with pytest.raises(ValueError, match="empty document"):
        await ingest_file("x.md", b"", doc_id="d", store=RecordingStore())


async def test_ingest_reads_utf8_content():
    store = RecordingStore()
    await ingest_file("cn.md", "中文文档内容，验证编码处理。".encode("utf-8"), doc_id="d", store=store)
    assert "中文文档内容" in store.upserted[0]["text"]


async def test_retriever_delegates_to_store():
    store = RecordingStore()
    retriever = Retriever(store=store)

    hits = await retriever.retrieve("查询内容", top_k=3)
    assert hits[0]["text"] == "命中片段"
    assert store.last_query == "查询内容"
    assert store.last_top_k == 3


async def test_retriever_default_top_k():
    store = RecordingStore()
    await Retriever(store=store).retrieve("q")
    assert store.last_top_k == 5


async def test_retriever_returns_empty_list_when_nothing_found():
    store = RecordingStore()
    store.search_results = []
    assert await Retriever(store=store).retrieve("q") == []
