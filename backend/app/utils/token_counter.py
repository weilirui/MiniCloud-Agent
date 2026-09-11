"""Token counting utilities (tiktoken-based)."""

from __future__ import annotations

import tiktoken

# Cache encodings
_ENCODING_CACHE: dict[str, tiktoken.Encoding] = {}


def get_encoding(model: str = "gpt-4o-mini") -> tiktoken.Encoding:
    """Get tiktoken encoding for a model, with fallback to cl100k_base."""
    if model in _ENCODING_CACHE:
        return _ENCODING_CACHE[model]

    try:
        enc = tiktoken.encoding_for_model(model)
    except KeyError:
        # Fallback for unknown / non-OpenAI models
        enc = tiktoken.get_encoding("cl100k_base")

    _ENCODING_CACHE[model] = enc
    return enc


def count_tokens(text: str, model: str = "gpt-4o-mini") -> int:
    """Count tokens in a string."""
    if not text:
        return 0
    enc = get_encoding(model)
    return len(enc.encode(text))


def count_message_tokens(messages: list[dict], model: str = "gpt-4o-mini") -> int:
    """Estimate tokens for a list of chat-format messages.

    Each message has overhead ~4 tokens for role delimiters.
    """
    enc = get_encoding(model)
    total = 0
    for msg in messages:
        # ~4 tokens per message for role/formatting
        total += 4
        content = msg.get("content") or ""
        if isinstance(content, str):
            total += len(enc.encode(content))
        elif isinstance(content, list):
            # multimodal content blocks
            for block in content:
                if isinstance(block, dict) and "text" in block:
                    total += len(enc.encode(block["text"]))

        # Tool calls contribute tokens too
        tool_calls = msg.get("tool_calls") or []
        for tc in tool_calls:
            fn = tc.get("function") or {}
            total += len(enc.encode(fn.get("name", "")))
            total += len(enc.encode(fn.get("arguments", "")))

        name = msg.get("name") or msg.get("tool_call_id") or ""
        if name:
            total += len(enc.encode(name))
    return total