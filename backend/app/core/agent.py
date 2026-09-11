"""Agent Loop: orchestrates LLM ↔ Tool execution.

The loop:
1. Build messages from context
2. Stream LLM response
3. If LLM requests tool calls, execute them and feed results back
4. Repeat until LLM stops or max iterations hit
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from app.config import settings
from app.core.context import ContextBuilder, summarize_messages
from app.core.llm import LLMClient, ToolCall, ToolSpec, get_llm_client
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AgentEvent:
    """An event emitted by the agent loop (yielded as SSE)."""

    type: str  # content / tool_call_start / tool_call_result / done / error
    data: dict = field(default_factory=dict)


@dataclass
class AgentDeps:
    """Dependencies injected into the Agent.

    Holds all tool sources: Skills, MCP, built-in tools.
    """

    skills_registry: Any = None  # app.skills.registry.SkillsRegistry
    mcp_manager: Any = None  # app.mcp.manager.MCPManager
    retriever: Any = None  # app.rag.retriever.Retriever
    session_id: UUID | None = None
    save_message: Any = None  # async callback to persist message
    save_tool_invocation: Any = None  # async callback to persist tool call


class Agent:
    """The Agent Loop."""

    def __init__(
        self,
        llm: LLMClient | None = None,
        deps: AgentDeps | None = None,
        model: str | None = None,
        max_iterations: int = settings.max_agent_iterations,
        max_context_tokens: int = settings.max_context_tokens,
    ):
        self.llm = llm or get_llm_client()
        self.deps = deps or AgentDeps()
        self.model = model or self.llm.model
        self.max_iterations = max_iterations
        self.ctx_builder = ContextBuilder(
            model=self.model,
            max_tokens=max_context_tokens,
        )

    def _collect_tools(self) -> list[ToolSpec]:
        """Collect all available tools from Skills + MCP + builtins."""
        tools: list[ToolSpec] = []

        # 1. Skills (name = "skill_<name>")
        if self.deps.skills_registry:
            for skill in self.deps.skills_registry.list():
                schema = skill.get_tool_schema()
                tools.append(ToolSpec(
                    name=schema["name"],
                    description=schema["description"],
                    parameters=schema["parameters"],
                    source="skill",
                ))

        # 2. MCP tools (name = "mcp__<server>__<tool>")
        if self.deps.mcp_manager:
            for mcp_tool in self.deps.mcp_manager.list_tools():
                tools.append(ToolSpec(
                    name=mcp_tool["name"],
                    description=mcp_tool.get("description", ""),
                    parameters=mcp_tool.get("parameters", {"type": "object", "properties": {}}),
                    source="mcp",
                ))

        # 3. Builtin: rag_search
        tools.append(ToolSpec(
            name="rag_search",
            description="从知识库检索相关文档片段。参数：query (string, 必填), top_k (int, 可选, 默认 5)",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索查询"},
                    "top_k": {"type": "integer", "description": "返回条数", "default": 5},
                },
                "required": ["query"],
            },
            source="builtin",
        ))

        return tools

    def _build_skills_summary(self) -> str:
        if not self.deps.skills_registry:
            return "（暂无）"
        from app.core.prompts import build_skills_summary
        return build_skills_summary([
            {"name": s.name, "description": s.description, "trigger": getattr(s, "trigger", None)}
            for s in self.deps.skills_registry.list()
        ])

    def _build_mcp_summary(self) -> str:
        if not self.deps.mcp_manager:
            return "（暂无）"
        from app.core.prompts import build_mcp_tools_summary
        return build_mcp_tools_summary(self.deps.mcp_manager.list_tools())

    async def _maybe_rag(self, user_query: str) -> list[dict] | None:
        """Optionally run RAG retrieval on user query."""
        if not self.deps.retriever:
            return None
        try:
            return await self.deps.retriever.retrieve(user_query, top_k=5)
        except Exception as e:
            logger.warning("rag_retrieval_failed", error=str(e))
            return None

    async def _execute_tool_call(self, tc: ToolCall) -> dict:
        """Dispatch a tool call to the appropriate handler."""
        start = time.time()
        name = tc.name
        args = tc.arguments

        result_text = ""
        status = "ok"
        error: str | None = None
        source = "unknown"

        try:
            if name.startswith("skill_"):
                skill_name = name[len("skill_"):]
                source = "skill"
                if not self.deps.skills_registry:
                    raise RuntimeError("skills registry not available")
                skill = self.deps.skills_registry.get(skill_name)
                if not skill:
                    raise RuntimeError(f"skill not found: {skill_name}")
                from app.skills.base import SkillContext
                ctx = SkillContext(
                    llm=self.llm,
                    session_id=str(self.deps.session_id) if self.deps.session_id else None,
                )
                result_text = await skill.invoke(ctx, **args)
                if not isinstance(result_text, str):
                    result_text = json.dumps(result_text, ensure_ascii=False)

            elif name.startswith("mcp__"):
                source = "mcp"
                parts = name[len("mcp__"):].split("__", 1)
                if len(parts) != 2:
                    raise RuntimeError(f"invalid mcp tool name: {name}")
                server_name, tool_name = parts
                if not self.deps.mcp_manager:
                    raise RuntimeError("mcp manager not available")
                result_text = await self.deps.mcp_manager.call_tool(server_name, tool_name, args)
                if not isinstance(result_text, str):
                    result_text = json.dumps(result_text, ensure_ascii=False)

            elif name == "rag_search":
                source = "builtin"
                query = args.get("query", "")
                top_k = args.get("top_k", 5)
                if not self.deps.retriever:
                    raise RuntimeError("retriever not available")
                results = await self.deps.retriever.retrieve(query, top_k=top_k)
                # Format for LLM
                if results:
                    result_text = "\n\n".join(
                        f"[{i+1}] {r.get('text', '')} (来源: {r.get('source', '?')}, score={r.get('score', 0):.3f})"
                        for i, r in enumerate(results)
                    )
                else:
                    result_text = "（未检索到相关结果）"

            else:
                raise RuntimeError(f"unknown tool: {name}")

        except Exception as e:
            status = "error"
            error = str(e)
            result_text = f"Error: {e}"
            logger.error("tool_call_failed", tool=name, error=str(e))

        duration_ms = int((time.time() - start) * 1000)

        # Persist invocation if callback provided
        if self.deps.save_tool_invocation and self.deps.session_id:
            try:
                await self.deps.save_tool_invocation(
                    session_id=self.deps.session_id,
                    source=source,
                    name=name,
                    arguments=args,
                    result=result_text[:5000],
                    status=status,
                    duration_ms=duration_ms,
                    error=error,
                )
            except Exception as e:
                logger.warning("save_tool_invocation_failed", error=str(e))

        return {
            "tool_call_id": tc.id,
            "name": name,
            "content": result_text,
            "status": status,
            "duration_ms": duration_ms,
        }

    async def run(
        self,
        messages: list[dict],
        system_prompt: str,
        summary: str = "",
    ) -> AsyncGenerator[AgentEvent, None]:
        """Run the agent loop and yield events.

        messages: history messages (without system) — already in OpenAI format.
        system_prompt: base system prompt.
        summary: existing history summary (may be updated mid-loop).
        """
        # Detect the latest user message for RAG retrieval
        user_query = ""
        for m in reversed(messages):
            if m.get("role") == "user" and m.get("content"):
                user_query = m["content"] if isinstance(m["content"], str) else ""
                break

        rag_context = await self._maybe_rag(user_query) if user_query else None

        skills_summary = self._build_skills_summary()
        mcp_summary = self._build_mcp_summary()
        tools = self._collect_tools()

        working_messages = self.ctx_builder.build_messages(
            system_prompt=system_prompt,
            messages=messages,
            skills_summary=skills_summary,
            mcp_tools_summary=mcp_summary,
            rag_context=rag_context,
            summary=summary,
        )

        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1

            # Stream LLM
            accumulated_content = ""
            tool_calls: list[ToolCall] = []
            current_tool_args: dict[int, str] = {}
            current_tool_ids: dict[int, str] = {}
            current_tool_names: dict[int, str] = {}
            finish_reason = "stop"

            yield AgentEvent(type="agent_iter_start", data={"iteration": iteration})

            async for chunk in self.llm.stream(working_messages, tools=tools):
                chunk_type = chunk.get("type")

                if chunk_type == "content":
                    delta = chunk.get("delta", "")
                    accumulated_content += delta
                    yield AgentEvent(type="content", data={"delta": delta})

                elif chunk_type == "tool_call_delta":
                    idx = chunk["index"]
                    current_tool_ids[idx] = chunk["id"]
                    if chunk.get("name"):
                        current_tool_names[idx] = chunk["name"]
                    current_tool_args[idx] = current_tool_args.get(idx, "") + chunk.get("arguments_delta", "")

                elif chunk_type == "tool_call_final":
                    tc = ToolCall(
                        id=chunk["id"],
                        name=chunk["name"],
                        arguments=chunk["arguments"],
                    )
                    tool_calls.append(tc)
                    yield AgentEvent(type="tool_call_start", data={
                        "id": tc.id,
                        "name": tc.name,
                        "arguments": tc.arguments,
                    })

                elif chunk_type == "finish":
                    finish_reason = chunk.get("finish_reason", "stop")

            # If no tool calls, we're done
            if not tool_calls:
                # Persist assistant message
                if self.deps.save_message and self.deps.session_id:
                    try:
                        await self.deps.save_message(
                            session_id=self.deps.session_id,
                            role="assistant",
                            content=accumulated_content,
                        )
                    except Exception as e:
                        logger.warning("save_message_failed", error=str(e))

                yield AgentEvent(type="done", data={
                    "finish_reason": finish_reason,
                    "content": accumulated_content,
                })
                return

            # Persist the assistant message with tool_calls
            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": accumulated_content or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    }
                    for tc in tool_calls
                ],
            }
            working_messages.append(assistant_msg)

            # Execute all tool calls in parallel
            results = await asyncio.gather(
                *[self._execute_tool_call(tc) for tc in tool_calls],
                return_exceptions=False,
            )

            # Append tool results to messages
            for r in results:
                working_messages.append({
                    "role": "tool",
                    "tool_call_id": r["tool_call_id"],
                    "name": r["name"],
                    "content": r["content"],
                })
                yield AgentEvent(type="tool_call_result", data=r)

            # Check context overflow and summarize if needed
            if self.ctx_builder.should_summarize(working_messages):
                logger.info("context_overflow_summarizing")
                # Take first half (excluding system) for summarization
                non_system = [m for m in working_messages if m.get("role") != "system"]
                head = non_system[:len(non_system) // 2]
                if head:
                    new_summary = await summarize_messages(head, self.llm)
                    # Replace with: system (summary), then keep tail
                    tail = non_system[len(non_system) // 2:]
                    working_messages = self.ctx_builder.build_messages(
                        system_prompt=system_prompt,
                        messages=tail,
                        skills_summary=skills_summary,
                        mcp_tools_summary=mcp_summary,
                        rag_context=None,  # already used
                        summary=summary + ("\n" + new_summary if summary else new_summary),
                    )

        # Max iterations reached
        yield AgentEvent(type="done", data={
            "finish_reason": "max_iterations",
            "content": accumulated_content,
        })