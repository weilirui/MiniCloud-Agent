"""Agent loop tests driven entirely by FakeLLM.

These tests wire several real components together (Agent + Skills registry +
ContextBuilder + callbacks) but touch no external service, so they run as part
of the normal suite - no ``--run-integration`` needed.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.core.agent import Agent, AgentDeps
from tests.fakes.fake_llm import FakeLLM, content_step, tool_step


class StubMCPManager:
    """Minimal stand-in for app.mcp.manager.MCPManager."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []

    def list_tools(self) -> list[dict]:
        return [
            {
                "name": "mcp__fs__read",
                "description": "读文件",
                "parameters": {"type": "object", "properties": {}},
                "server": "fs",
                "original_name": "read",
            }
        ]

    async def call_tool(self, server: str, name: str, arguments: dict) -> str:
        self.calls.append((server, name, arguments))
        return f"file-content:{arguments.get('path', '')}"


class StubRetriever:
    def __init__(self, results: list[dict] | None = None) -> None:
        # NB: `results or [...]` would silently replace an intentionally empty
        # result set with the defaults.
        self.results = (
            [
                {"text": "检索片段A", "source": "doc1", "score": 0.9},
                {"text": "检索片段B", "source": "doc2", "score": 0.8},
            ]
            if results is None
            else results
        )
        self.queries: list[str] = []

    async def retrieve(self, query: str, top_k: int = 5, **_: Any) -> list[dict]:
        self.queries.append(query)
        return self.results[:top_k]


async def collect(agent: Agent, messages: list[dict], system_prompt: str = "SYS"):
    events = []
    async for ev in agent.run(messages=messages, system_prompt=system_prompt):
        events.append(ev)
    return events


def types(events) -> list[str]:
    return [e.type for e in events]


# --------------------------------------------------------------------------

async def test_plain_answer_emits_content_then_done():
    llm = FakeLLM(script=[content_step("你好，有什么可以帮你？")])
    agent = Agent(llm=llm, deps=AgentDeps())

    events = await collect(agent, [{"role": "user", "content": "hi"}])

    assert types(events)[-1] == "done"
    assert "".join(e.data["delta"] for e in events if e.type == "content") == "你好，有什么可以帮你？"
    assert events[-1].data["finish_reason"] == "stop"


async def test_agent_executes_skill_and_feeds_result_back(skill_registry):
    llm = FakeLLM(
        script=[
            tool_step("skill_echo", {"text": "ping"}),
            content_step("回声完成"),
        ]
    )
    deps = AgentDeps(skills_registry=skill_registry)
    agent = Agent(llm=llm, deps=deps)

    events = await collect(agent, [{"role": "user", "content": "echo ping"}])

    results = [e for e in events if e.type == "tool_call_result"]
    assert len(results) == 1
    assert results[0].data["name"] == "skill_echo"
    assert results[0].data["status"] == "ok"
    assert "ping" in results[0].data["content"]
    assert types(events).count("agent_iter_start") == 2


async def test_agent_routes_mcp_tool_calls():
    mcp = StubMCPManager()
    llm = FakeLLM(
        script=[
            tool_step("mcp__fs__read", {"path": "/tmp/a.txt"}),
            content_step("读完了"),
        ]
    )
    agent = Agent(llm=llm, deps=AgentDeps(mcp_manager=mcp))

    events = await collect(agent, [{"role": "user", "content": "读文件"}])

    assert mcp.calls == [("fs", "read", {"path": "/tmp/a.txt"})]
    result = next(e for e in events if e.type == "tool_call_result")
    assert "file-content:/tmp/a.txt" in result.data["content"]


async def test_builtin_rag_search_tool():
    retriever = StubRetriever()
    llm = FakeLLM(
        script=[
            tool_step("rag_search", {"query": "RAG 参数"}),
            content_step("根据检索结果回答"),
        ]
    )
    agent = Agent(llm=llm, deps=AgentDeps(retriever=retriever))

    events = await collect(agent, [{"role": "user", "content": "RAG 参数是多少"}])

    result = next(e for e in events if e.type == "tool_call_result")
    assert "检索片段A" in result.data["content"]
    assert "RAG 参数" in retriever.queries  # auto-retrieval on user query too


async def test_rag_search_with_no_hits_returns_notice():
    llm = FakeLLM(script=[tool_step("rag_search", {"query": "x"}), content_step("ok")])
    agent = Agent(llm=llm, deps=AgentDeps(retriever=StubRetriever(results=[])))

    events = await collect(agent, [{"role": "user", "content": "x"}])
    result = next(e for e in events if e.type == "tool_call_result")
    assert "未检索到" in result.data["content"]


async def test_unknown_tool_is_reported_as_error():
    """A tool name matching no known prefix must not crash the loop."""
    llm = FakeLLM(script=[tool_step("totally_unknown_tool", {}), content_step("失败后的兜底")])
    agent = Agent(llm=llm, deps=AgentDeps())

    events = await collect(agent, [{"role": "user", "content": "x"}])
    result = next(e for e in events if e.type == "tool_call_result")

    assert result.data["status"] == "error"
    assert "unknown tool" in result.data["content"]
    assert events[-1].data["finish_reason"] == "stop"


async def test_skill_call_without_a_registry_is_reported_as_error():
    llm = FakeLLM(script=[tool_step("skill_nope", {}), content_step("兜底")])
    agent = Agent(llm=llm, deps=AgentDeps())

    events = await collect(agent, [{"role": "user", "content": "x"}])
    result = next(e for e in events if e.type == "tool_call_result")

    assert result.data["status"] == "error"
    assert "registry not available" in result.data["content"]


async def test_invalid_mcp_tool_name_is_reported_as_error():
    llm = FakeLLM(script=[tool_step("mcp__broken", {}), content_step("done")])
    agent = Agent(llm=llm, deps=AgentDeps(mcp_manager=StubMCPManager()))

    events = await collect(agent, [{"role": "user", "content": "x"}])
    result = next(e for e in events if e.type == "tool_call_result")
    assert result.data["status"] == "error"
    assert "invalid mcp tool name" in result.data["content"]


async def test_max_iterations_stops_the_loop():
    script = [tool_step("rag_search", {"query": "loop"}, call_id=f"c{i}") for i in range(20)]
    llm = FakeLLM(script=script)
    agent = Agent(llm=llm, deps=AgentDeps(retriever=StubRetriever()), max_iterations=3)

    events = await collect(agent, [{"role": "user", "content": "loop"}])

    assert events[-1].type == "done"
    assert events[-1].data["finish_reason"] == "max_iterations"
    assert types(events).count("agent_iter_start") == 3


async def test_persistence_callbacks_are_invoked():
    saved_messages = []
    saved_tools = []

    async def save_message(**kwargs):
        saved_messages.append(kwargs)

    async def save_tool_invocation(**kwargs):
        saved_tools.append(kwargs)

    session_id = uuid.uuid4()
    llm = FakeLLM(script=[tool_step("rag_search", {"query": "x"}), content_step("最终答案")])
    deps = AgentDeps(
        retriever=StubRetriever(),
        session_id=session_id,
        save_message=save_message,
        save_tool_invocation=save_tool_invocation,
    )
    agent = Agent(llm=llm, deps=deps)

    await collect(agent, [{"role": "user", "content": "x"}])

    assert any(m["role"] == "assistant" and m["content"] == "最终答案" for m in saved_messages)
    assert len(saved_tools) == 1
    assert saved_tools[0]["name"] == "rag_search"
    assert saved_tools[0]["session_id"] == session_id
    assert saved_tools[0]["status"] == "ok"


async def test_summarization_triggers_when_over_budget():
    """With a tiny budget the loop must ask the model to summarize mid-flight."""
    llm = FakeLLM(
        script=[
            tool_step("rag_search", {"query": "x"}),
            {"content": "这是一段压缩后的历史摘要"},  # summarize_messages -> chat()
            content_step("继续回答"),
        ]
    )
    agent = Agent(
        llm=llm,
        deps=AgentDeps(retriever=StubRetriever()),
        max_context_tokens=1,  # forces should_summarize() == True every iteration
    )

    await collect(
        agent,
        [{"role": "user", "content": "很长很长的问题" * 30}],
    )

    # one call for the loop, plus one chat() call for the summarization step
    assert len(llm.calls) >= 2


async def test_tools_are_collected_from_all_sources(skill_registry):
    agent = Agent(
        llm=FakeLLM(),
        deps=AgentDeps(skills_registry=skill_registry, mcp_manager=StubMCPManager()),
    )
    names = {t.name for t in agent._collect_tools()}

    assert "skill_echo" in names
    assert "mcp__fs__read" in names
    assert "rag_search" in names


async def test_collected_tools_carry_source_metadata(skill_registry):
    agent = Agent(llm=FakeLLM(), deps=AgentDeps(skills_registry=skill_registry))
    sources = {t.name: t.source for t in agent._collect_tools()}
    assert sources["skill_echo"] == "skill"
    assert sources["rag_search"] == "builtin"


async def test_llm_error_propagates():
    from app.utils.errors import LLMError

    llm = FakeLLM(script=[{"error": "api exploded"}])
    agent = Agent(llm=llm, deps=AgentDeps())

    with pytest.raises(LLMError):
        await collect(agent, [{"role": "user", "content": "x"}])


async def test_parallel_tool_calls_all_execute():
    llm = FakeLLM(
        script=[
            {
                "tool_calls": [
                    {"id": "a", "name": "rag_search", "arguments": {"query": "q1"}},
                    {"id": "b", "name": "rag_search", "arguments": {"query": "q2"}},
                ]
            },
            content_step("两个都查了"),
        ]
    )
    retriever = StubRetriever()
    agent = Agent(llm=llm, deps=AgentDeps(retriever=retriever))

    events = await collect(agent, [{"role": "user", "content": "查两个"}])
    results = [e for e in events if e.type == "tool_call_result"]

    assert len(results) == 2
    assert {r.data["tool_call_id"] for r in results} == {"a", "b"}
    assert len(retriever.queries) == 3  # 1 auto + 2 explicit
