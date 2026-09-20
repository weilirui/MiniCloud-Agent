"""Tests for the evaluation metric implementations."""

from __future__ import annotations

import pytest

from eval.metrics.agent import (
    avg_steps,
    evaluate_agent_traces,
    task_success,
    tool_selection_accuracy,
    tool_selection_exact_match,
)
from eval.metrics.generation import citation_rate, lexical_support


# ------------------------------------------------------------- agent metrics


def test_tool_selection_accuracy_is_jaccard():
    # |{b}| / |{a, b, c}| = 1/3
    assert tool_selection_accuracy(["a", "b"], ["b", "c"]) == pytest.approx(1 / 3)
    assert tool_selection_accuracy(["a"], ["a"]) == 1.0
    assert tool_selection_accuracy([], []) == 1.0


def test_tool_selection_accuracy_no_expected_but_tools_called():
    """A chatty task (no tool expected) is penalised if tools were used."""
    assert tool_selection_accuracy(["skill_echo"], []) == 0.0


def test_tool_selection_exact_match_requires_set_equality():
    assert tool_selection_exact_match(["a", "b"], ["b", "a"]) == 1.0
    assert tool_selection_exact_match(["a"], ["a", "b"]) == 0.0


def test_task_success_needs_every_required_string():
    assert task_success("文件路径是 agent.py", ["agent.py"]) == 1.0
    assert task_success("文件路径是 agent.py", ["agent.py", "第 12 行"]) == 0.0


def test_avg_steps_counts_tool_calls():
    assert avg_steps([["a"], ["a", "b", "c"]]) == 2.0
    assert avg_steps([]) == 0.0


def test_evaluate_agent_traces_ignores_tasks_without_must_contain():
    """Tasks that only assert routing must not be counted as content failures.

    Otherwise ``task_success_rate`` mostly measures how many eval tasks
    happened to declare ``must_contain``, not how good the agent is.
    """
    traces = [
        {"tools": ["skill_echo"], "final": "hello world", "expected_tools": ["skill_echo"], "must_contain": ["hello world"]},
        {"tools": ["rag_search"], "final": "……", "expected_tools": ["rag_search"], "must_contain": []},
        {"tools": [], "final": "余弦相似度……", "expected_tools": [], "must_contain": ["余弦"]},
    ]

    scores = evaluate_agent_traces(traces)

    assert scores["task_success_n"] == 2.0
    assert scores["task_success_rate"] == 1.0
    # Routing accuracy still covers all three traces.
    assert scores["tool_selection_acc"] == 1.0


def test_evaluate_agent_traces_reports_none_when_nothing_scorable():
    traces = [{"tools": [], "final": "x", "expected_tools": [], "must_contain": []}]

    scores = evaluate_agent_traces(traces)

    assert scores["task_success_rate"] is None
    assert scores["task_success_n"] == 0.0


def test_evaluate_agent_traces_empty_input():
    assert evaluate_agent_traces([]) == {}


@pytest.mark.parametrize(
    ("answer", "contexts", "expected"),
    [
        ("余弦相似度用于向量检索", ["余弦相似度用于向量检索"], 1.0),
        ("余弦相似度用于向量检索", [], 0.0),
        ("", ["任意内容"], 0.0),
    ],
)
def test_lexical_support(answer, contexts, expected):
    assert lexical_support(answer, contexts) == expected


def test_lexical_support_partial_coverage():
    answer = "熔断器的状态机"
    contexts = ["熔断器有三种状态"]
    # "的" and "状态机" are not fully covered by the context tokens.
    assert 0.0 < lexical_support(answer, contexts) < 1.0


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("参见 [来源 1]", 1.0),
        ("参见 [来源1]", 1.0),
        ("没有引用", 0.0),
        ("", 0.0),
    ],
)
def test_citation_rate(answer, expected):
    assert citation_rate(answer) == expected
