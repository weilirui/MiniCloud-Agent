"""Storage keeps the provider tool-call shape; the UI needs a flatter one.

If these two ever drift, reloading a session silently renders nameless tool
cards - the bug that ``_flatten_tool_calls`` exists to prevent.
"""

from __future__ import annotations

from app.api.sessions import _flatten_tool_calls


def test_openai_shape_is_flattened_for_the_ui():
    raw = [
        {
            "id": "call_a",
            "type": "function",
            "function": {"name": "rag_search", "arguments": '{"query": "熔断器"}'},
        }
    ]

    assert _flatten_tool_calls(raw) == [
        {"id": "call_a", "name": "rag_search", "arguments": {"query": "熔断器"}}
    ]


def test_arguments_already_dict_pass_through():
    raw = [{"id": "c", "type": "function", "function": {"name": "x", "arguments": {"a": 1}}}]

    assert _flatten_tool_calls(raw)[0]["arguments"] == {"a": 1}


def test_unparsable_arguments_stay_visible_instead_of_being_dropped():
    """A truncated stream must not turn into an empty arguments panel."""
    raw = [{"id": "c", "type": "function", "function": {"name": "x", "arguments": "{not json"}}]

    assert _flatten_tool_calls(raw)[0]["arguments"] == {"_raw": "{not json"}


def test_empty_payloads_return_none():
    assert _flatten_tool_calls(None) is None
    assert _flatten_tool_calls([]) is None
