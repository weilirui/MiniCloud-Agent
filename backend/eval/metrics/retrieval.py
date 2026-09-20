"""Retrieval metrics: recall@k, precision@k, MRR, nDCG@k, hit-rate."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence


def _truncate(retrieved: Sequence[str], k: int) -> list[str]:
    return list(retrieved)[:k]


def precision_at_k(retrieved: Sequence[str], relevant: Iterable[str], k: int = 5) -> float:
    """Fraction of the top-k results that are relevant."""
    if k <= 0:
        return 0.0
    rel = set(relevant)
    top = _truncate(retrieved, k)
    if not top:
        return 0.0
    return sum(1 for doc in top if doc in rel) / len(top)


def recall_at_k(retrieved: Sequence[str], relevant: Iterable[str], k: int = 5) -> float:
    """Fraction of all relevant chunks found within the top-k."""
    rel = set(relevant)
    if not rel:
        return 0.0
    top = _truncate(retrieved, k)
    return sum(1 for doc in top if doc in rel) / len(rel)


def hit_rate_at_k(retrieved: Sequence[str], relevant: Iterable[str], k: int = 5) -> float:
    """1.0 if at least one relevant chunk is in the top-k, else 0.0."""
    rel = set(relevant)
    return 1.0 if any(doc in rel for doc in _truncate(retrieved, k)) else 0.0


def reciprocal_rank(retrieved: Sequence[str], relevant: Iterable[str]) -> float:
    """1 / rank of the first relevant result (0 if none)."""
    rel = set(relevant)
    for rank, doc in enumerate(retrieved, start=1):
        if doc in rel:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved: Sequence[str], relevant: Iterable[str], k: int = 5) -> float:
    """Normalized discounted cumulative gain with binary relevance."""
    rel = set(relevant)
    top = _truncate(retrieved, k)
    if not rel or not top:
        return 0.0
    dcg = sum(
        (1.0 if doc in rel else 0.0) / math.log2(rank + 1)
        for rank, doc in enumerate(top, start=1)
    )
    ideal_hits = min(len(rel), len(top))
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return dcg / idcg if idcg else 0.0


def evaluate_retrieval(
    runs: dict[str, list[str]],
    goldens: dict[str, set[str]],
    ks: Sequence[int] = (1, 3, 5),
) -> dict[str, float]:
    """Average every metric over a set of queries.

    ``runs``   : query_id -> ranked list of retrieved chunk ids
    ``goldens``: query_id -> set of relevant chunk ids
    """
    if not runs:
        return {}

    out: dict[str, float] = {}
    for k in ks:
        out[f"recall@{k}"] = _mean(
            recall_at_k(runs[q], goldens.get(q, set()), k) for q in runs
        )
        out[f"precision@{k}"] = _mean(
            precision_at_k(runs[q], goldens.get(q, set()), k) for q in runs
        )
        out[f"hit_rate@{k}"] = _mean(
            hit_rate_at_k(runs[q], goldens.get(q, set()), k) for q in runs
        )
    out["mrr"] = _mean(reciprocal_rank(runs[q], goldens.get(q, set())) for q in runs)
    out["ndcg@5"] = _mean(ndcg_at_k(runs[q], goldens.get(q, set()), 5) for q in runs)
    out["queries"] = float(len(runs))
    return {key: round(value, 4) for key, value in out.items()}


def _mean(values: Iterable[float]) -> float:
    vals = list(values)
    return sum(vals) / len(vals) if vals else 0.0
