"""Generation quality metrics.

Two flavours, because you cannot always afford a judge:

- ``lexical_support``    - offline, deterministic: how much of the answer is
  backed by the retrieved context (token containment).
- ``llm_faithfulness``   - LLM-as-judge, 0..1, used when a real key is present.
"""

from __future__ import annotations

from app.rag.lexical import tokenize

JUDGE_PROMPT = """你是评测助手。判断下面的回答是否完全由给定材料支持（不引入材料之外的断言）。

材料：
{context}

回答：
{answer}

只输出一个 0 到 1 之间的小数，1 表示完全被材料支持，0 表示完全编造。不要输出任何其他内容。"""


def lexical_support(answer: str, contexts: list[str]) -> float:
    """Fraction of answer tokens that appear in the retrieved context."""
    answer_tokens = set(tokenize(answer))
    if not answer_tokens:
        return 0.0
    context_tokens: set[str] = set()
    for ctx in contexts:
        context_tokens |= set(tokenize(ctx))
    covered = len(answer_tokens & context_tokens)
    return round(covered / len(answer_tokens), 4)


def citation_rate(answer: str) -> float:
    """1.0 when the answer cites a source (``[来源 N]`` / ``[来源1]``)."""
    import re

    return 1.0 if re.search(r"\[来源\s*\d+\]", answer or "") else 0.0


async def llm_faithfulness(answer: str, contexts: list[str], llm_client) -> float:
    """LLM-as-judge faithfulness in [0, 1]. Returns 0.0 when it cannot judge."""
    if not answer or not contexts:
        return 0.0
    prompt = JUDGE_PROMPT.format(context="\n\n".join(contexts), answer=answer)
    try:
        resp = await llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=16,
        )
    except Exception:
        return 0.0

    import re

    match = re.search(r"(\d(?:.\d+)?)", (resp.content or "").strip())
    if not match:
        return 0.0
    try:
        value = float(match.group(1))
    except ValueError:
        return 0.0
    return round(min(max(value, 0.0), 1.0), 4)


def evaluate_generation(
    samples: list[dict],
    *,
    judge=None,
) -> dict[str, float]:
    """Aggregate generation metrics.

    ``samples``: [{"answer": str, "contexts": [str, ...]}, ...]
    """
    if not samples:
        return {}

    supports = [lexical_support(s.get("answer", ""), s.get("contexts", [])) for s in samples]
    citations = [citation_rate(s.get("answer", "")) for s in samples]
    return {
        "samples": float(len(samples)),
        "lexical_support": round(sum(supports) / len(supports), 4),
        "citation_rate": round(sum(citations) / len(citations), 4),
    }
