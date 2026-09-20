"""Agent trajectory metrics: did it pick the right tools and finish the job?"""

from __future__ import annotations

from collections.abc import Iterable, Sequence


def tool_selection_accuracy(predicted: Sequence[str], expected: Iterable[str]) -> float:
    """Jaccard overlap between the tools actually called and the expected set."""
    pred, exp = set(predicted), set(expected)
    if not exp:
        return 1.0 if not pred else 0.0
    if not pred:
        return 0.0
    return len(pred & exp) / len(pred | exp)


def tool_selection_exact_match(predicted: Sequence[str], expected: Iterable[str]) -> float:
    """1.0 only when the predicted tool set equals the expected one."""
    return 1.0 if set(predicted) == set(expected) else 0.0


def task_success(final_answer: str, must_contain: Iterable[str]) -> float:
    """1.0 when every required string appears in the final answer."""
    required = [m for m in must_contain if m]
    if not required:
        return 0.0
    return 1.0 if all(m in (final_answer or "") for m in required) else 0.0


def avg_steps(trajectories: Sequence[Sequence[str]]) -> float:
    """Average number of tool calls per task."""
    if not trajectories:
        return 0.0
    return sum(len(t) for t in trajectories) / len(trajectories)


def evaluate_agent_traces(traces: list[dict]) -> dict[str, float]:
    """Aggregate agent metrics.

    ``traces``: [{"tools": [...], "final": str, "expected_tools": [...],
                  "must_contain": [...]}, ...]
    """
    if not traces:
        return {}

    acc = [tool_selection_accuracy(t.get("tools", []), t.get("expected_tools", [])) for t in traces]
    exact = [tool_selection_exact_match(t.get("tools", []), t.get("expected_tools", [])) for t in traces]
    success = [task_success(t.get("final", ""), t.get("must_contain", [])) for t in traces]
    steps = [len(t.get("tools", [])) for t in traces]

    return {
        "tasks": float(len(traces)),
        "tool_selection_acc": round(sum(acc) / len(acc), 4),
        "tool_selection_exact": round(sum(exact) / len(exact), 4),
        "task_success_rate": round(sum(success) / len(success), 4),
        "avg_steps": round(sum(steps) / len(steps), 4),
        "max_steps": float(max(steps)),
    }
