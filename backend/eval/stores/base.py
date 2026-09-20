"""Vector store abstraction used by the evaluation runner."""

from __future__ import annotations

import math
from typing import Any, Protocol


class VectorStore(Protocol):
    """Minimal surface the retrieval evaluation needs."""

    async def add(self, chunks: list[dict[str, Any]]) -> None:
        """Index chunks: {"id", "text", "source", "metadata"}."""

    async def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Return [{"id", "text", "source", "score", "metadata"}, ...]."""

    async def clear(self) -> None:
        """Drop everything (used between strategies / reruns)."""


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)
