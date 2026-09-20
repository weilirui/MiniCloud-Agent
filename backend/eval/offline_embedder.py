"""Deterministic offline embedder for reproducible evaluation.

Real embedding APIs cost money and can change between model versions, which
makes a retrieval benchmark impossible to reproduce in CI. This embedder does
a seeded random projection of the token bag, so the same text always yields the
same vector - good enough to compare retrieval *strategies* against each other.

It is NOT a semantic model. Numbers produced with it are only meaningful as a
relative comparison (vector vs hybrid vs hybrid+MMR), never as an absolute
quality score. For absolute numbers, run the eval against Qdrant with the real
embedding model (``--backend qdrant``).
"""

from __future__ import annotations

import hashlib
import math
import random
from functools import lru_cache

from app.rag.lexical import tokenize


@lru_cache(maxsize=20000)
def _token_vector(token: str, dim: int, seed: int) -> tuple[float, ...]:
    digest = hashlib.md5(f"{seed}:{token}".encode("utf-8")).hexdigest()
    rng = random.Random(int(digest[:16], 16))
    return tuple(rng.gauss(0.0, 1.0) for _ in range(dim))


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return vec
    return [v / norm for v in vec]


class HashingEmbedder:
    """Offline, dependency-free, deterministic text embedder."""

    def __init__(self, dim: int = 128, seed: int = 20240920) -> None:
        self.dim = dim
        self.seed = seed

    def embed_sync(self, text: str) -> list[float]:
        tokens = tokenize(text)
        if not tokens:
            return [0.0] * self.dim
        acc = [0.0] * self.dim
        for tok in tokens:
            vec = _token_vector(tok, self.dim, self.seed)
            for i in range(self.dim):
                acc[i] += vec[i]
        return _l2_normalize([v / len(tokens) for v in acc])

    async def embed_one(self, text: str) -> list[float]:
        return self.embed_sync(text)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_sync(t) for t in texts]
