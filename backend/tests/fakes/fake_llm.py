"""FakeLLM: a scripted stand-in for ``app.core.llm.LLMClient``.

This is the piece of infrastructure that makes the Agent loop testable.
Without it, every test of ``Agent.run`` would either hit a paid API or assert
nothing. With it, we can say "the model will ask for this tool, then answer"
and assert on the exact loop behaviour - iteration count, tool routing,
message assembly, context summarization.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

from app.core.llm import LLMResponse, ToolCall
from app.utils.errors import LLMError


def content_step(text: str) -> dict[str, Any]:
    """Script step: the model answers with plain text."""
    return {"content": text}


def tool_step(name: str, arguments: dict | None = None, call_id: str = "call_1") -> dict[str, Any]:
    """Script step: the model requests one tool call."""
    return {
        "tool_calls": [
            {"id": call_id, "name": name, "arguments": arguments or {}}
        ]
    }


def error_step(message: str = "boom") -> dict[str, Any]:
    """Script step: the model blows up."""
    return {"error": message}


class FakeLLM:
    """Replays a script of model responses, recording every call it received."""

    def __init__(
        self,
        script: list[dict[str, Any]] | None = None,
        model: str = "fake-mini",
        usage: dict[str, int] | None = None,
    ) -> None:
        self.model = model
        self.script: list[dict[str, Any]] = [dict(s) for s in (script or [])]
        self.usage = usage or {"prompt_tokens": 16, "completion_tokens": 8}
        #: every call: {"messages": [...], "tools": [...]}
        self.calls: list[dict[str, Any]] = []
        self._cursor = 0

    # ---------- script handling ----------

    def push(self, *steps: dict[str, Any]) -> "FakeLLM":
        self.script.extend(dict(s) for s in steps)
        return self

    def _next(self) -> dict[str, Any]:
        if self._cursor >= len(self.script):
            return {"content": ""}
        step = self.script[self._cursor]
        self._cursor += 1
        return step

    # ---------- LLMClient surface ----------

    async def chat(
        self,
        messages: list[dict],
        tools: list[Any] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        self.calls.append({"messages": list(messages), "tools": tools})
        step = self._next()

        if step.get("error"):
            raise LLMError(step["error"])

        tool_calls = [
            ToolCall(**tc) if not isinstance(tc, ToolCall) else tc
            for tc in step.get("tool_calls", [])
        ]
        return LLMResponse(
            content=step.get("content"),
            tool_calls=tool_calls,
            finish_reason="tool_calls" if tool_calls else "stop",
            usage=dict(self.usage),
        )

    async def stream(
        self,
        messages: list[dict],
        tools: list[Any] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        self.calls.append({"messages": list(messages), "tools": tools})
        step = self._next()

        if step.get("error"):
            raise LLMError(step["error"])

        # tool_call deltas first (mirrors real providers: deltas, then finish)
        for idx, tc in enumerate(step.get("tool_calls", [])):
            yield {
                "type": "tool_call_delta",
                "index": idx,
                "id": tc["id"],
                "name": tc["name"],
                "arguments_delta": json.dumps(tc.get("arguments", {}), ensure_ascii=False),
            }

        # content is emitted in small pieces so accumulation is exercised
        for piece in _chunk(step.get("content") or "", 8):
            yield {"type": "content", "delta": piece}

        for tc in step.get("tool_calls", []):
            yield {
                "type": "tool_call_final",
                "id": tc["id"],
                "name": tc["name"],
                "arguments": tc.get("arguments", {}),
            }

        yield {
            "type": "finish",
            "finish_reason": "tool_calls" if step.get("tool_calls") else "stop",
        }


def _chunk(text: str, size: int) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)] or []
