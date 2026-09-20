"""Unit tests for token counting - the basis of every context-window decision."""

from __future__ import annotations

from app.utils.token_counter import count_message_tokens, count_tokens, get_encoding


def test_count_tokens_positive_for_ascii():
    assert count_tokens("hello world") > 0


def test_count_tokens_empty_string_is_zero():
    assert count_tokens("") == 0


def test_count_tokens_grows_with_length():
    short = count_tokens("a short sentence")
    long = count_tokens("a short sentence " * 50)
    assert long > short


def test_unknown_model_falls_back_to_cl100k():
    enc = get_encoding("definitely-not-a-real-model-v1")
    assert enc is not None
    # cl100k_base encodes the same string identically to the fallback path
    assert count_tokens("上下文压缩", model="definitely-not-a-real-model-v1") > 0


def test_count_message_tokens_adds_per_message_overhead():
    messages = [{"role": "user", "content": "hi"}]
    assert count_message_tokens(messages) == 4 + count_tokens("hi")


def test_count_message_tokens_counts_tool_calls():
    plain = [{"role": "assistant", "content": "ok"}]
    with_tools = [
        {
            "role": "assistant",
            "content": "ok",
            "tool_calls": [
                {"function": {"name": "rag_search", "arguments": '{"query": "x"}'}}
            ],
        }
    ]
    assert count_message_tokens(with_tools) > count_message_tokens(plain)


def test_count_message_tokens_handles_multimodal_blocks():
    messages = [
        {
            "role": "user",
            "content": [{"type": "text", "text": "描述这张图"}],
        }
    ]
    assert count_message_tokens(messages) > 4


def test_count_message_tokens_empty_list():
    assert count_message_tokens([]) == 0
