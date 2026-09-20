"""Local semantic embeddings for evaluation.

Why this exists
---------------
The offline :class:`~eval.offline_embedder.HashingEmbedder` is a seeded random
projection. It is reproducible and dependency-free, but it carries no semantics
— so any recall number produced with it only ranks strategies relative to each
other, and cannot be quoted as an absolute figure.

This module wraps ``fastembed`` so the same golden set can be scored with a
real sentence-embedding model (``BAAI/bge-small-zh-v1.5``, 512-d, ~55 MB)
running locally through ONNX Runtime. No API key, no per-run cost, fully
reproducible, and the numbers are meaningful in absolute terms.
"""

from __future__ import annotations

import os
import sys
from typing import Sequence

DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"

# The default cache lives under the OS temp dir, where interrupted downloads
# leave zero-byte files behind that then fail with a confusing
# "ModelProto does not have a graph". Anchor it to the interpreter prefix
# instead: that is writable wherever the venv is, and shared by every run.
DEFAULT_CACHE_DIR = os.environ.get(
    "FASTEMBED_CACHE_DIR", os.path.join(sys.prefix, "fastembed_cache")
)


class LocalEmbedder:
    """Adapter exposing the ``EmbeddingClient`` surface used by eval stores."""

    def __init__(self, model_name: str = DEFAULT_MODEL, cache_dir: str | None = None) -> None:
        from fastembed import TextEmbedding

        self.model_name = model_name
        os.makedirs(cache_dir or DEFAULT_CACHE_DIR, exist_ok=True)
        self._model = TextEmbedding(model_name=model_name, cache_dir=cache_dir or DEFAULT_CACHE_DIR)
        # fastembed resolves the real dimension only after the weights load.
        probe = next(iter(self._model.embed(["维度探测"])))
        self.dim = len(probe)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"LocalEmbedder(model={self.model_name}, dim={self.dim})"

    def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self._model.embed(list(texts))]

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._encode(texts)

    async def embed_one(self, text: str) -> list[float]:
        if not text:
            return []
        return self._encode([text])[0]
