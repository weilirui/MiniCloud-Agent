"""Build ``golden_retrieval.jsonl`` from the corpus + query seed files.

The golden set is derived, not hand-written: each query names a target
document and a list of keywords, and the chunk(s) of that document that match
the most keywords become the relevant chunk ids. Re-run this script whenever
the corpus or the chunking parameters change.

Usage (from ``backend/``):
    python scripts/build_golden_dataset.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.rag.chunker import chunk_text  # noqa: E402
from app.rag.lexical import tokenize  # noqa: E402

DATASETS = Path(__file__).resolve().parents[1] / "eval" / "datasets"
CHUNK_SIZE = 180
CHUNK_OVERLAP = 40


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def keyword_hits(chunk_text_value: str, keywords: list[str]) -> int:
    tokens = set(tokenize(chunk_text_value))
    lowered = chunk_text_value.lower()
    hits = 0
    for kw in keywords:
        if kw.lower() in lowered or kw.lower() in tokens:
            hits += 1
    return hits


def main() -> int:
    corpus = load_jsonl(DATASETS / "corpus.jsonl")
    queries = load_jsonl(DATASETS / "queries.jsonl")

    chunks_by_doc: dict[str, list[dict]] = {}
    for doc in corpus:
        pieces = chunk_text(doc["text"], chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
        chunks_by_doc[doc["doc_id"]] = [
            {
                "id": f"{doc['doc_id']}::{idx}",
                "text": piece.text,
                "source": doc["doc_id"],
                "metadata": {"title": doc["title"], "chunk_index": idx},
            }
            for idx, piece in enumerate(pieces)
        ]

    lines: list[str] = []
    stats = Counter()
    for query in queries:
        doc_id = query["doc_id"]
        keywords = query.get("keywords", [])
        chunks = chunks_by_doc.get(doc_id, [])
        if not chunks:
            stats["no_chunks"] += 1
            continue

        scored = [(keyword_hits(c["text"], keywords), c["id"]) for c in chunks]
        best = max(score for score, _ in scored)
        if best <= 0:
            relevant = [cid for _, cid in scored]
            stats["fallback_all"] += 1
        else:
            relevant = [cid for score, cid in scored if score == best]
            stats["matched"] += 1

        lines.append(
            json.dumps(
                {
                    "query_id": query["query_id"],
                    "query": query["query"],
                    "doc_id": doc_id,
                    "relevant_chunk_ids": relevant,
                },
                ensure_ascii=False,
            )
        )

    out_path = DATASETS / "golden_retrieval.jsonl"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    total_chunks = sum(len(v) for v in chunks_by_doc.values())
    print(f"corpus docs      : {len(corpus)}")
    print(f"chunks           : {total_chunks} (size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP})")
    print(f"queries          : {len(queries)}")
    print(f"golden written   : {len(lines)} -> {out_path}")
    print(f"  keyword-matched: {stats['matched']}")
    print(f"  fallback-all   : {stats['fallback_all']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
