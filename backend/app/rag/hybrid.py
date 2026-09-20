"""Hybrid retrieval: dense + lexical fusion, then MMR diversification.

Pipeline
--------
1. Dense branch  : Qdrant vector search  -> ``top_k * candidate_multiplier`` hits
2. Lexical branch: BM25 keyword search   -> ``top_k * candidate_multiplier`` hits
3. Fusion        : weighted normalized score (default) or Reciprocal Rank Fusion
4. Diversify     : MMR re-ranking so near-duplicate chunks don't eat the budget

The diversity step is intentionally lexical (token Jaccard) instead of
embedding-based: it costs zero extra API calls and needs no extra dependency.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.rag.lexical import LexicalIndex, tokenize
from app.utils.logging import get_logger

logger = get_logger(__name__)

#: Dense/lexical searchers return plain dicts: id / text / score / source / metadata
VectorSearcher = Callable[..., Awaitable[list[dict[str, Any]]]]


def hit_id(hit: dict[str, Any]) -> str:
    """Resolve a stable chunk id from a dense-search hit.

    Adapters do not agree on the field name. ``eval.stores`` emit ``id``, while
    the production ``app.rag.qdrant_store`` only carries ``doc_id`` +
    ``chunk_index``. Keying fusion on a single hard-coded name therefore breaks
    silently the moment a different adapter is plugged in, so resolve in
    priority order and fall back to a digest of the text.
    """
    for key in ("id", "chunk_id", "point_id"):
        value = hit.get(key)
        if value:
            return str(value)

    doc_id = hit.get("doc_id")
    if doc_id:
        return f"{doc_id}#{hit.get('chunk_index', 0)}"

    text = hit.get("text") or ""
    if not text:
        return ""
    digest = hashlib.blake2b(text.encode("utf-8"), digest_size=8).hexdigest()
    return f"text:{digest}"


@dataclass
class Candidate:
    """A retrieval candidate belonging to one document chunk."""

    id: str
    text: str
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    vector_score: float = 0.0
    lexical_score: float = 0.0
    fused_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "source": self.source,
            "score": self.fused_score,
            "vector_score": self.vector_score,
            "lexical_score": self.lexical_score,
            "metadata": self.metadata,
        }


@dataclass
class HybridConfig:
    """Tunables for hybrid retrieval."""

    vector_weight: float = 0.7
    lexical_weight: float = 0.3
    candidate_multiplier: int = 4
    fusion: str = "weighted"  # "weighted" | "rrf"
    rrf_k: int = 60
    enable_mmr: bool = True
    mmr_lambda: float = 0.7


def normalize(scores: list[float]) -> list[float]:
    """Min-max normalize a list of scores into [0, 1]."""
    if not scores:
        return []
    lo, hi = min(scores), max(scores)
    if math.isclose(hi, lo):
        return [1.0 if s > 0 else 0.0 for s in scores]
    return [(s - lo) / (hi - lo) for s in scores]


def rrf_fuse(rank_lists: list[list[str]], k: int = 60) -> dict[str, float]:
    """Reciprocal Rank Fusion: ``score(d) = sum(1 / (k + rank_i(d)))``."""
    fused: dict[str, float] = {}
    for ranks in rank_lists:
        for rank, doc_id in enumerate(ranks, start=1):
            fused[doc_id] = fused.get(doc_id, 0.0) + 1.0 / (k + rank)
    return fused


def jaccard(a: set[str], b: set[str]) -> float:
    """Token-set Jaccard similarity."""
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if not inter:
        return 0.0
    return inter / len(a | b)


def mmr_select(
    items: list[Candidate],
    top_k: int,
    lambda_: float = 0.7,
    *,
    token_sets: dict[str, set[str]] | None = None,
) -> list[Candidate]:
    """Maximal Marginal Relevance selection.

    Iteratively pick the candidate maximizing
    ``lambda * relevance - (1 - lambda) * max_similarity_to_already_picked``.
    """
    if len(items) <= top_k:
        return list(items)

    tokens = token_sets or {c.id: set(tokenize(c.text)) for c in items}
    remaining = list(items)
    selected: list[Candidate] = []

    while remaining and len(selected) < top_k:
        best: Candidate | None = None
        best_value = -math.inf
        for cand in remaining:
            relevance = cand.fused_score
            if selected:
                redundancy = max(
                    jaccard(tokens.get(cand.id, set()), tokens.get(s.id, set()))
                    for s in selected
                )
            else:
                redundancy = 0.0
            value = lambda_ * relevance - (1 - lambda_) * redundancy
            if value > best_value:
                best_value = value
                best = cand
        if best is None:  # pragma: no cover - defensive
            break
        selected.append(best)
        remaining.remove(best)

    return selected


def fuse_candidates(
    vector_hits: list[dict[str, Any]],
    lexical_hits: list[tuple[str, float]],
    config: HybridConfig,
    *,
    text_lookup: Callable[[str], str] | None = None,
) -> list[Candidate]:
    """Merge the two ranked lists into a single fused candidate list."""
    candidates: dict[str, Candidate] = {}

    def get(cand_id: str, **defaults: Any) -> Candidate:
        cand = candidates.get(cand_id)
        if cand is None:
            metadata = dict(defaults.get("metadata") or {})
            # Keep the originating doc/chunk addressable for citation even when
            # the adapter did not surface it through a dedicated ``id`` field.
            for key in ("doc_id", "chunk_index"):
                if defaults.get(key) is not None and key not in metadata:
                    metadata[key] = defaults[key]
            cand = Candidate(
                id=cand_id,
                text=defaults.get("text") or (text_lookup(cand_id) if text_lookup else ""),
                source=defaults.get("source", ""),
                metadata=metadata,
            )
            candidates[cand_id] = cand
        return cand

    # Resolve ids once; a hit we cannot key is dropped rather than collapsed
    # into a shared "" bucket alongside every other unkeyable hit.
    keyed_hits = [(hit_id(h), h) for h in vector_hits]
    keyed_hits = [(cid, h) for cid, h in keyed_hits if cid]

    if config.fusion == "rrf":
        fused = rrf_fuse(
            [[cid for cid, _ in keyed_hits], [doc_id for doc_id, _ in lexical_hits]],
            k=config.rrf_k,
        )
        for cand_id, hit in keyed_hits:
            get(
                cand_id,
                text=hit.get("text", ""),
                source=hit.get("source", ""),
                metadata=hit.get("metadata", {}),
                doc_id=hit.get("doc_id"),
                chunk_index=hit.get("chunk_index"),
            ).vector_score = float(hit.get("score", 0.0))
        for doc_id, score in lexical_hits:
            get(doc_id).lexical_score = float(score)
        for doc_id, score in fused.items():
            get(doc_id).fused_score = score
    else:
        vec_scores = normalize([float(h.get("score", 0.0)) for _, h in keyed_hits])
        lex_scores = normalize([float(s) for _, s in lexical_hits])
        for (cand_id, hit), norm in zip(keyed_hits, vec_scores):
            get(
                cand_id,
                text=hit.get("text", ""),
                source=hit.get("source", ""),
                metadata=hit.get("metadata", {}),
                doc_id=hit.get("doc_id"),
                chunk_index=hit.get("chunk_index"),
            ).vector_score = norm
        for (doc_id, raw), norm in zip(lexical_hits, lex_scores):
            get(doc_id).lexical_score = norm
        for cand in candidates.values():
            cand.fused_score = (
                config.vector_weight * cand.vector_score
                + config.lexical_weight * cand.lexical_score
            )

    out = list(candidates.values())
    out.sort(key=lambda c: c.fused_score, reverse=True)
    return out


class HybridRetriever:
    """Dense + lexical hybrid retriever with MMR diversification."""

    def __init__(
        self,
        vector_search: VectorSearcher,
        lexical_index: LexicalIndex | None = None,
        config: HybridConfig | None = None,
    ) -> None:
        self.vector_search = vector_search
        self.lexical_index = lexical_index
        self.config = config or HybridConfig()

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Retrieve ``top_k`` chunks using the hybrid pipeline."""
        cfg = self.config
        fetch_k = max(top_k, top_k * cfg.candidate_multiplier)

        vector_hits: list[dict[str, Any]] = []
        try:
            vector_hits = await self.vector_search(query, top_k=fetch_k, **kwargs)
        except Exception as exc:  # dense branch is allowed to fail
            logger.warning("hybrid_vector_branch_failed", error=str(exc))

        # Lexical branch is pointless without an index; degrade to dense-only.
        if self.lexical_index is None or self.lexical_index.size == 0:
            return [self._as_output(h) for h in vector_hits][:top_k]

        lexical_hits = self.lexical_index.search(query, top_k=fetch_k)
        text_lookup = self.lexical_index.text_of

        merged = fuse_candidates(
            vector_hits, lexical_hits, cfg, text_lookup=text_lookup
        )

        if cfg.enable_mmr:
            merged = mmr_select(merged, top_k=top_k, lambda_=cfg.mmr_lambda)
        else:
            merged = merged[:top_k]

        return [c.to_dict() for c in merged]

    @staticmethod
    def _as_output(hit: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": hit_id(hit),
            "text": hit.get("text", ""),
            "source": hit.get("source", ""),
            "score": float(hit.get("score", 0.0)),
            "vector_score": float(hit.get("score", 0.0)),
            "lexical_score": 0.0,
            "metadata": hit.get("metadata", {}),
        }
