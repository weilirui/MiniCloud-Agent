"""Unit tests for document chunking and file-type detection."""

from __future__ import annotations

from app.rag.chunker import (
    chunk_text,
    detect_file_type,
    load_file_content,
)


def test_empty_text_produces_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n  ") == []


def test_short_text_stays_single_chunk():
    chunks = chunk_text("这是一段很短的文本。", chunk_size=800)
    assert len(chunks) == 1
    assert chunks[0].index == 0


def test_long_text_is_split_into_multiple_chunks():
    text = "。".join(f"第{i}段内容，用于验证切分行为是否正常" for i in range(60))
    chunks = chunk_text(text, chunk_size=200, chunk_overlap=0)
    assert len(chunks) > 1
    assert all(len(c.text) <= 200 * 1.5 for c in chunks)


def test_chunks_are_indexed_sequentially():
    text = "。".join(f"段落{i}" for i in range(40))
    chunks = chunk_text(text, chunk_size=120, chunk_overlap=20)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_overlap_carries_context_forward():
    text = "开头锚点。" + "中间填充内容。" * 40 + "结尾锚点。"
    chunks = chunk_text(text, chunk_size=150, chunk_overlap=40)
    assert len(chunks) > 1
    # at least one chunk after the first should start with tail of the previous
    assert any(chunks[i + 1].text.startswith(chunks[i].text[-40:]) for i in range(len(chunks) - 1))


def test_overlap_disabled_keeps_chunks_disjoint():
    text = "。".join(f"内容{i}" for i in range(60))
    chunks_no_overlap = chunk_text(text, chunk_size=150, chunk_overlap=0)
    chunks_overlap = chunk_text(text, chunk_size=150, chunk_overlap=50)
    assert sum(len(c.text) for c in chunks_overlap) >= sum(len(c.text) for c in chunks_no_overlap)


def test_chunk_metadata_tracks_offsets():
    chunks = chunk_text("第一段内容。" * 30, chunk_size=100, chunk_overlap=0)
    for chunk in chunks:
        assert "char_start" in chunk.metadata
        assert "char_end" in chunk.metadata
        assert chunk.metadata["char_end"] >= chunk.metadata["char_start"]


def test_detect_file_type():
    assert detect_file_type("README.md") == "markdown"
    assert detect_file_type("main.py") == "code"
    assert detect_file_type("App.tsx") == "code"
    assert detect_file_type("config.yaml") == "code"
    assert detect_file_type("paper.pdf") == "pdf"
    assert detect_file_type("notes.txt") == "text"


def test_load_file_content_decodes_utf8():
    assert load_file_content("a.md", "你好 RAG".encode("utf-8")) == "你好 RAG"


def test_load_file_content_falls_back_on_bad_encoding():
    raw = "中文内容".encode("gbk")
    assert "中" in load_file_content("a.txt", raw)
