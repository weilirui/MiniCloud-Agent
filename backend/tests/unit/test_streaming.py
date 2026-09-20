"""Unit tests for SSE packing helpers."""

from __future__ import annotations

import json

from app.utils.streaming import format_chat_chunk, sse_pack, sse_stream


def test_sse_pack_shape():
    assert sse_pack("content", {"delta": "hi"}) == 'event: content\ndata: {"delta": "hi"}\n\n'


def test_sse_pack_accepts_preformatted_string():
    assert sse_pack("done", "bye") == "event: done\ndata: bye\n\n"


def test_sse_pack_keeps_unicode_readable():
    packed = sse_pack("content", {"delta": "中文"})
    assert "中文" in packed
    assert "\\u" not in packed


def test_sse_pack_payload_is_valid_json():
    packed = sse_pack("tool_call_result", {"name": "rag_search", "status": "ok"})
    data_line = [line for line in packed.splitlines() if line.startswith("data: ")][0]
    assert json.loads(data_line[len("data: "):])["name"] == "rag_search"


async def test_sse_stream_yields_packed_events():
    async def source():
        yield {"event": "content", "data": {"delta": "a"}}
        yield {"event": "done", "data": {"finish_reason": "stop"}}

    out = [chunk async for chunk in sse_stream(source())]
    assert out[0].startswith("event: content")
    assert out[1].startswith("event: done")


async def test_sse_stream_defaults_event_name():
    async def source():
        yield {"data": {"delta": "a"}}

    out = [chunk async for chunk in sse_stream(source())]
    assert out[0].startswith("event: message")


def test_format_chat_chunk_carries_all_fields():
    chunk = format_chat_chunk(
        content="答案", tool_call={"name": "x"}, finish_reason="stop", message_id="m1"
    )
    assert chunk == {
        "content": "答案",
        "tool_call": {"name": "x"},
        "finish_reason": "stop",
        "message_id": "m1",
    }


def test_format_chat_chunk_defaults_to_none():
    chunk = format_chat_chunk()
    assert all(v is None for v in chunk.values())
