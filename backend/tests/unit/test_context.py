"""Unit tests for context assembly and summarization."""

from __future__ import annotations

import pytest

from app.core.context import ContextBuilder, summarize_messages
from tests.fakes.fake_llm import FakeLLM, error_step


def test_build_messages_puts_system_first():
    builder = ContextBuilder(max_tokens=8000)
    out = builder.build_messages(
        system_prompt="SYS",
        messages=[{"role": "user", "content": "hi"}],
    )
    assert out[0]["role"] == "system"
    assert out[0]["content"].startswith("SYS")


def test_build_messages_keeps_only_recent_messages():
    builder = ContextBuilder(max_tokens=8000, max_recent_messages=3)
    messages = [{"role": "user", "content": f"m{i}"} for i in range(10)]
    out = builder.build_messages(system_prompt="SYS", messages=messages)
    contents = [m["content"] for m in out if m["role"] == "user"]
    assert contents == ["m7", "m8", "m9"]


def test_skills_summary_is_appended_but_placeholder_is_not():
    builder = ContextBuilder()
    with_skill = builder.build_messages(
        system_prompt="SYS",
        messages=[],
        skills_summary="- `/echo` —— 回显",
    )
    assert "可用 Skills" in with_skill[0]["content"]

    with_placeholder = builder.build_messages(
        system_prompt="SYS",
        messages=[],
        skills_summary="（暂无）",
    )
    assert "可用 Skills" not in with_placeholder[0]["content"]


def test_mcp_summary_is_appended():
    builder = ContextBuilder()
    out = builder.build_messages(
        system_prompt="SYS",
        messages=[],
        mcp_tools_summary="- `mcp__fs__read` —— 读文件",
    )
    assert "可用 MCP 工具" in out[0]["content"]


def test_rag_context_is_injected_with_citation_hint():
    builder = ContextBuilder()
    out = builder.build_messages(
        system_prompt="SYS",
        messages=[],
        rag_context=[{"text": "片段A"}, {"text": "片段B"}],
    )
    system = out[0]["content"]
    assert "知识库检索结果" in system
    assert "片段A" in system and "片段B" in system
    assert "[来源 N]" in system


def test_history_summary_becomes_its_own_system_message():
    builder = ContextBuilder()
    out = builder.build_messages(
        system_prompt="SYS", messages=[], summary="之前聊过 RAG"
    )
    assert any(m["role"] == "system" and "历史摘要" in m["content"] for m in out)


def test_should_summarize_respects_budget():
    builder = ContextBuilder(max_tokens=50)
    assert builder.should_summarize([{"role": "user", "content": "x" * 4000}]) is True
    assert builder.should_summarize([{"role": "user", "content": "hi"}]) is False


def test_needs_trim_compares_against_window():
    builder = ContextBuilder(max_recent_messages=2)
    messages = [{"role": "user", "content": str(i)} for i in range(5)]
    assert builder.needs_trim(messages) is True
    assert builder.needs_trim(messages[:2]) is False


async def test_summarize_messages_uses_llm_response():
    llm = FakeLLM(script=[{"content": "压缩后的摘要"}])
    result = await summarize_messages([{"role": "user", "content": "很长的一段对话"}], llm)
    assert result == "压缩后的摘要"


async def test_summarize_messages_falls_back_when_llm_fails():
    llm = FakeLLM(script=[error_step("api down")])
    result = await summarize_messages([{"role": "user", "content": "内容A"}], llm)
    assert "内容A" in result
    assert result.endswith("...")


async def test_summarize_messages_empty_input():
    assert await summarize_messages([], FakeLLM()) == ""


def test_estimate_tokens_matches_token_counter():
    from app.utils.token_counter import count_message_tokens

    builder = ContextBuilder()
    messages = [{"role": "user", "content": "hello"}]
    assert builder.estimate_tokens(messages) == count_message_tokens(messages, model=builder.model)


@pytest.mark.parametrize("max_tokens", [10, 100, 10000])
def test_should_summarize_is_monotonic_in_budget(max_tokens):
    builder = ContextBuilder(max_tokens=max_tokens)
    messages = [{"role": "user", "content": "a" * 400}]
    if max_tokens == 10:
        assert builder.should_summarize(messages) is True
    else:
        assert builder.should_summarize(messages) is False
