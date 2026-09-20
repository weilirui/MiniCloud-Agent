"""Unit tests for working / long-term memory."""

from __future__ import annotations

import pytest

from app.core.memory import LongTermMemory, WorkingMemory


def test_add_message_appends_with_extra_fields():
    mem = WorkingMemory(session_id="s-1")
    mem.add_message("user", "你好")
    mem.add_message("tool", "结果", tool_call_id="call_1")

    assert mem.messages[0] == {"role": "user", "content": "你好"}
    assert mem.messages[1]["tool_call_id"] == "call_1"


def test_trim_keeps_only_the_tail():
    mem = WorkingMemory(session_id="s-1", max_recent=3)
    for i in range(10):
        mem.add_message("user", f"m{i}")
    mem.trim()

    assert [m["content"] for m in mem.messages] == ["m7", "m8", "m9"]


def test_trim_is_a_noop_below_limit():
    mem = WorkingMemory(session_id="s-1", max_recent=5)
    mem.add_message("user", "only one")
    mem.trim()
    assert len(mem.messages) == 1


def test_to_messages_prepends_system_and_summary():
    mem = WorkingMemory(session_id="s-1", system_prompt="SYS", summary="之前聊过 RAG")
    mem.add_message("user", "继续")

    out = mem.to_messages()
    assert out[0] == {"role": "system", "content": "SYS"}
    assert "历史摘要" in out[1]["content"]
    assert out[-1] == {"role": "user", "content": "继续"}


def test_to_messages_without_system_or_summary():
    mem = WorkingMemory(session_id="s-1")
    mem.add_message("user", "hi")
    assert mem.to_messages() == [{"role": "user", "content": "hi"}]


def test_clear_wipes_messages_and_summary():
    mem = WorkingMemory(session_id="s-1", summary="摘要")
    mem.add_message("user", "hi")
    mem.clear()
    assert mem.messages == []
    assert mem.summary == ""


async def test_long_term_memory_is_a_declared_placeholder():
    """Long-term memory is not wired yet - it must fail loudly, not silently."""
    ltm = LongTermMemory()
    with pytest.raises(NotImplementedError):
        await ltm.store("k", "v")
    with pytest.raises(NotImplementedError):
        await ltm.retrieve("q")
