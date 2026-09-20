"""Dependency-free lexical retrieval (BM25) with CJK support.

Pure vector search misses exact terms (identifiers, error strings, Chinese
proper nouns). This module provides a small BM25 index so retrieval can be
hybrid: dense (Qdrant) + lexical (BM25).
"""

from __future__ import annotations

import math
import re
from collections import Counter

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    """Tokenize text for both latin and Chinese content.

    Latin runs are kept as whole words; CJK characters become unigrams plus
    bigrams, which makes Chinese matching usable without a word segmenter.
    """
    if not text:
        return []

    raw = _TOKEN_RE.findall(text.lower())
    tokens: list[str] = []
    for i, tok in enumerate(raw):
        tokens.append(tok)
        nxt = raw[i + 1] if i + 1 < len(raw) else ""
        if _CJK_RE.match(tok) and nxt and _CJK_RE.match(nxt):
            tokens.append(tok + nxt)
    return tokens


class BM25:
    """Okapi BM25 over an in-memory list of documents."""

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._doc_tokens: list[list[str]] = []
        self._doc_len: list[int] = []
        self._tf: list[Counter] = []
        self._df: Counter = Counter()
        self._avgdl = 0.0
        self._n = 0

    @property
    def size(self) -> int:
        return self._n

    def fit(self, docs: list[str]) -> "BM25":
        """Build the index from a list of raw documents."""
        self._doc_tokens = [tokenize(d) for d in docs]
        self._doc_len = [len(t) for t in self._doc_tokens]
        self._tf = [Counter(t) for t in self._doc_tokens]
        self._n = len(self._doc_tokens)
        self._avgdl = (sum(self._doc_len) / self._n) if self._n else 0.0

        self._df = Counter()
        for toks in self._doc_tokens:
            self._df.update(set(toks))
        return self

    def _idf(self, term: str) -> float:
        df = self._df.get(term, 0)
        return math.log(1 + (self._n - df + 0.5) / (df + 0.5))

    def scores(self, query: str) -> list[float]:
        """BM25 score of every indexed document against ``query``."""
        if not self._n:
            return []

        q_tokens = tokenize(query)
        out = [0.0] * self._n
        for term in q_tokens:
            idf = self._idf(term)
            if idf <= 0:
                continue
            for idx in range(self._n):
                freq = self._tf[idx].get(term, 0)
                if not freq:
                    continue
                dl = self._doc_len[idx] or 1
                denom = freq + self.k1 * (1 - self.b + self.b * dl / (self._avgdl or 1.0))
                out[idx] += idf * (freq * (self.k1 + 1)) / denom
        return out

    def top_k(self, query: str, k: int = 10, min_score: float = 0.0) -> list[tuple[int, float]]:
        """Return ``[(doc_index, score), ...]`` sorted by score desc."""
        scored = [(i, s) for i, s in enumerate(self.scores(query)) if s > min_score]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]


class LexicalIndex:
    """BM25 index keyed by document id (chunk id / point id)."""

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self._ids: list[str] = []
        self._texts: dict[str, str] = {}
        self._bm25 = BM25(k1=k1, b=b)
        self._dirty = True

    @property
    def size(self) -> int:
        return len(self._ids)

    def add(self, doc_id: str, text: str) -> None:
        if doc_id in self._texts:
            self._texts[doc_id] = text
        else:
            self._ids.append(doc_id)
            self._texts[doc_id] = text
        self._dirty = True

    def build(self) -> "LexicalIndex":
        """(Re)build the underlying BM25 index."""
        self._bm25.fit([self._texts[i] for i in self._ids])
        self._dirty = False
        return self

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        """Return ``[(doc_id, score), ...]`` sorted by score desc."""
        if self._dirty:
            self.build()
        hits = self._bm25.top_k(query, k=top_k)
        return [(self._ids[idx], score) for idx, score in hits]

    def text_of(self, doc_id: str) -> str:
        return self._texts.get(doc_id, "")
