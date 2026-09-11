"""SSE (Server-Sent Events) helpers."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any


def sse_pack(event: str, data: Any) -> str:
    """Pack a single SSE message."""
    payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


async def sse_stream(
    source: AsyncGenerator[dict, None],
) -> AsyncGenerator[str, None]:
    """Wrap an async generator of dicts as SSE events.

    Each dict should have keys: 'event' (str) and 'data' (Any).
    """
    async for chunk in source:
        event = chunk.get("event", "message")
        data = chunk.get("data")
        yield sse_pack(event, data)


def format_chat_chunk(
    content: str | None = None,
    tool_call: dict | None = None,
    finish_reason: str | None = None,
    message_id: str | None = None,
) -> dict:
    """Format a chat chunk for SSE."""
    return {
        "content": content,
        "tool_call": tool_call,
        "finish_reason": finish_reason,
        "message_id": message_id,
    }