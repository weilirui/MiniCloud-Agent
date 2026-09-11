"""OpenAI-compatible LLM client wrapper.

Supports: chat completion (sync/async/streaming), tool calling.
Works with OpenAI, DeepSeek, Qwen, Moonshot, etc.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI

from app.config import settings
from app.utils.errors import LLMError
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ToolSpec:
    """A tool available to the LLM (in OpenAI tools schema format)."""

    name: str
    description: str
    parameters: dict = field(default_factory=lambda: {"type": "object", "properties": {}})
    source: str = "builtin"  # builtin / skill / mcp


@dataclass
class ToolCall:
    """An LLM tool call request."""

    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    """A complete LLM response."""

    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict = field(default_factory=dict)
    raw: Any = None


class LLMClient:
    """Async OpenAI-compatible LLM client.

    Provides chat() and stream() methods.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_key = api_key or settings.openai_api_key
        self.base_url = base_url or settings.openai_base_url
        self.model = model or settings.openai_model
        self._client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

    async def chat(
        self,
        messages: list[dict],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Non-streaming chat completion."""
        kwargs = self._build_kwargs(messages, tools, temperature, max_tokens, stream=False)
        try:
            resp = await self._client.chat.completions.create(**kwargs)
        except Exception as e:
            logger.error("llm_chat_failed", error=str(e))
            raise LLMError(f"LLM call failed: {e}") from e

        choice = resp.choices[0]
        msg = choice.message
        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args,
                ))

        return LLMResponse(
            content=msg.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage=resp.usage.model_dump() if resp.usage else {},
            raw=resp,
        )

    async def stream(
        self,
        messages: list[dict],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Streaming chat completion.

        Yields dicts of the form:
          {"type": "content", "delta": "..."}
          {"type": "tool_call", "id": "...", "name": "...", "arguments_delta": "..."}
          {"type": "finish", "finish_reason": "..."}
        """
        kwargs = self._build_kwargs(messages, tools, temperature, max_tokens, stream=True)

        # Accumulate tool call deltas
        tool_call_accumulators: dict[int, dict] = {}

        try:
            stream = await self._client.chat.completions.create(**kwargs)
        except Exception as e:
            logger.error("llm_stream_failed", error=str(e))
            raise LLMError(f"LLM stream failed: {e}") from e

        async for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta

            # Content delta
            if delta.content:
                yield {"type": "content", "delta": delta.content}

            # Tool call deltas
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_call_accumulators:
                        tool_call_accumulators[idx] = {
                            "id": tc.id or "",
                            "name": "",
                            "arguments": "",
                        }
                    acc = tool_call_accumulators[idx]
                    if tc.id:
                        acc["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            acc["name"] = tc.function.name
                        if tc.function.arguments:
                            acc["arguments"] += tc.function.arguments
                    yield {
                        "type": "tool_call_delta",
                        "index": idx,
                        "id": acc["id"],
                        "name": acc["name"],
                        "arguments_delta": tc.function.arguments if tc.function else "",
                    }

            # Finish
            if choice.finish_reason:
                # Emit accumulated tool calls as final events
                for idx, acc in tool_call_accumulators.items():
                    if acc["name"]:
                        try:
                            args = json.loads(acc["arguments"] or "{}")
                        except json.JSONDecodeError:
                            args = {}
                        yield {
                            "type": "tool_call_final",
                            "id": acc["id"],
                            "name": acc["name"],
                            "arguments": args,
                        }
                yield {"type": "finish", "finish_reason": choice.finish_reason}

    def _build_kwargs(
        self,
        messages: list[dict],
        tools: list[ToolSpec] | None,
        temperature: float,
        max_tokens: int | None,
        stream: bool,
    ) -> dict:
        """Build kwargs for OpenAI client call."""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }
        if max_tokens:
            kwargs["max_tokens"] = max_tokens

        if tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
        return kwargs


# Singleton
_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client