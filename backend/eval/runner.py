"""Retrieval evaluation runner.

Compares three retrieval strategies on the same golden set:

- ``vector``      dense search only (the baseline the project shipped with)
- ``hybrid``      dense + BM25, weighted score fusion
- ``hybrid_mmr``  dense + BM25 + MMR diversification

Outputs a Markdown report and a JSON blob under ``eval/reports/``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

from app.rag.chunker import chunk_text
from app.rag.hybrid import HybridConfig, HybridRetriever
from app.rag.lexical import LexicalIndex
from eval.metrics.retrieval import evaluate_retrieval
from eval.offline_embedder import HashingEmbedder
from eval.stores.memory import InMemoryVectorStore
from eval.stores.qdrant import QdrantEvalStore

DATASETS = Path(__file__).parent / "datasets"
REPORTS = Path(__file__).parent / "reports"

STRATEGIES = ("vector", "hybrid", "hybrid_mmr")
METRIC_ORDER = ("recall@1", "recall@3", "recall@5", "precision@5", "hit_rate@5", "mrr", "ndcg@5")


# --------------------------------------------------------------------------
# data loading
# --------------------------------------------------------------------------

def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def build_chunks(corpus: list[dict], chunk_size: int, overlap: int) -> list[dict[str, Any]]:
    """Chunk every corpus document into eval chunks with stable ids."""
    chunks: list[dict[str, Any]] = []
    for doc in corpus:
        pieces = chunk_text(doc["text"], chunk_size=chunk_size, chunk_overlap=overlap)
        for idx, piece in enumerate(pieces):
            chunks.append(
                {
                    "id": f"{doc['doc_id']}::{idx}",
                    "text": piece.text,
                    "source": doc["doc_id"],
                    "metadata": {"title": doc.get("title", ""), "chunk_index": idx},
                }
            )
    return chunks


def build_lexical_index(chunks: list[dict[str, Any]]) -> LexicalIndex:
    index = LexicalIndex()
    for chunk in chunks:
        index.add(chunk["id"], chunk["text"])
    return index.build()


# --------------------------------------------------------------------------
# strategies
# --------------------------------------------------------------------------

async def run_strategy(
    store: Any,
    lexical_index: LexicalIndex,
    strategy: str,
    queries: list[str],
    top_k: int,
) -> list[list[str]]:
    """Run one strategy over all queries, returning ranked chunk-id lists."""
    if strategy == "vector":
        results = [await store.search(q, top_k=top_k) for q in queries]
        return [[hit["id"] for hit in hits] for hits in results]

    retriever = HybridRetriever(
        vector_search=store.search,
        lexical_index=lexical_index,
        config=HybridConfig(enable_mmr=(strategy == "hybrid_mmr")),
    )
    out: list[list[str]] = []
    for query in queries:
        hits = await retriever.retrieve(query, top_k=top_k)
        out.append([hit["id"] for hit in hits])
    return out


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------

def render_markdown(
    scores: dict[str, dict[str, float]],
    meta: dict[str, Any],
    baseline: str = "vector",
) -> str:
    lines: list[str] = []
    lines.append("# 检索评测报告")
    lines.append("")
    lines.append(f"- 生成时间：{meta['generated_at']}")
    lines.append(f"- 检索后端：**{meta['backend']}**")
    lines.append(f"- 语料：{meta['docs']} 篇文档 / {meta['chunks']} 个文本块"
                 f"（chunk_size={meta['chunk_size']}, overlap={meta['overlap']}）")
    lines.append(f"- 查询集：{meta['queries']} 条")
    lines.append(f"- top_k：{meta['top_k']}")
    lines.append("")

    header = "| 策略 | " + " | ".join(METRIC_ORDER) + " |"
    lines.append(header)
    lines.append("|" + "---|" * (len(METRIC_ORDER) + 1))

    base = scores.get(baseline, {})
    for strategy in STRATEGIES:
        row = scores.get(strategy)
        if not row:
            continue
        cells = []
        for metric in METRIC_ORDER:
            value = row.get(metric, 0.0)
            cell = f"{value:.4f}"
            if strategy != baseline and metric in base and base[metric]:
                delta = value - base[metric]
                cell += f" ({delta:+.4f})"
            cells.append(cell)
        lines.append(f"| `{strategy}` | " + " | ".join(cells) + " |")

    lines.append("")
    lines.append("括号中是与基线 `vector` 的差值。")
    lines.append("")

    if meta.get("backend") == "memory":
        lines.append(
            "> 注意：本报告使用离线哈希向量（HashingEmbedder）代替真实 embedding，"
            "**只能用于策略之间的相对比较**，不能当作绝对检索质量。"
            "要拿绝对数值，请跑 `python -m eval.runner --backend qdrant`。"
        )
        lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

async def evaluate(
    backend: str = "memory",
    top_k: int = 5,
    chunk_size: int = 180,
    overlap: int = 40,
    collection: str = "minicloud_kb_eval",
    qdrant_url: str | None = None,
    embedder: str = "offline",
) -> dict[str, Any]:
    corpus = load_jsonl(DATASETS / "corpus.jsonl")
    golden_rows = load_jsonl(DATASETS / "golden_retrieval.jsonl")
    if not golden_rows:
        raise SystemExit("golden_retrieval.jsonl is empty - run scripts/build_golden_dataset.py first")

    chunks = build_chunks(corpus, chunk_size, overlap)
    lexical_index = build_lexical_index(chunks)
    goldens = {row["query_id"]: set(row["relevant_chunk_ids"]) for row in golden_rows}
    queries = [row["query"] for row in golden_rows]
    query_ids = [row["query_id"] for row in golden_rows]

    if embedder == "openai":
        from app.rag.embeddings import get_embedding_client

        embedding: Any = get_embedding_client()
    else:
        embedding = HashingEmbedder()

    if backend == "qdrant":
        # ``settings.qdrant_url`` defaults to the in-Docker hostname
        # (http://qdrant:6333), which does not resolve from the host - so the
        # host-side port has to be passed explicitly when running outside compose.
        store: Any = QdrantEvalStore(collection=collection, url=qdrant_url, embedding=embedding)
        await store.clear()
    else:
        store = InMemoryVectorStore(embedding)

    started = time.time()
    await store.add(chunks)

    scores: dict[str, dict[str, float]] = {}
    raw_runs: dict[str, dict[str, list[str]]] = {}
    for strategy in STRATEGIES:
        ranked = await run_strategy(store, lexical_index, strategy, queries, top_k)
        runs = dict(zip(query_ids, ranked))
        raw_runs[strategy] = runs
        scores[strategy] = evaluate_retrieval(runs, goldens, ks=(1, 3, 5))

    elapsed = round(time.time() - started, 2)
    meta = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "backend": backend,
        "docs": len(corpus),
        "chunks": len(chunks),
        "queries": len(queries),
        "top_k": top_k,
        "chunk_size": chunk_size,
        "overlap": overlap,
        "elapsed_seconds": elapsed,
    }
    return {"meta": meta, "scores": scores, "runs": raw_runs}


def write_reports(result: dict[str, Any]) -> tuple[Path, Path]:
    REPORTS.mkdir(parents=True, exist_ok=True)
    md_path = REPORTS / "eval_report.md"
    json_path = REPORTS / "eval_report.json"

    md_path.write_text(
        render_markdown(result["scores"], result["meta"]), encoding="utf-8"
    )
    json_path.write_text(
        json.dumps(
            {"meta": result["meta"], "scores": result["scores"]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return md_path, json_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the retrieval evaluation")
    parser.add_argument("--backend", choices=("memory", "qdrant"), default="memory")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--chunk-size", type=int, default=180)
    parser.add_argument("--overlap", type=int, default=40)
    parser.add_argument("--collection", default="minicloud_kb_eval")
    parser.add_argument(
        "--qdrant-url",
        default=os.environ.get("QDRANT_URL", "http://localhost:16333"),
        help="Qdrant HTTP endpoint as seen from where the runner executes",
    )
    parser.add_argument(
        "--embedder",
        choices=("offline", "openai"),
        default="offline",
        help="'openai' costs money but produces absolute-quality numbers",
    )
    args = parser.parse_args()

    result = asyncio.run(
        evaluate(
            backend=args.backend,
            top_k=args.top_k,
            chunk_size=args.chunk_size,
            overlap=args.overlap,
            collection=args.collection,
            qdrant_url=args.qdrant_url,
            embedder=args.embedder,
        )
    )
    md_path, json_path = write_reports(result)

    print(f"backend={args.backend} chunks={result['meta']['chunks']} queries={result['meta']['queries']}")
    for strategy in STRATEGIES:
        row = result["scores"].get(strategy, {})
        print(
            f"  {strategy:<11} recall@5={row.get('recall@5', 0):.4f} "
            f"mrr={row.get('mrr', 0):.4f} ndcg@5={row.get('ndcg@5', 0):.4f}"
        )
    print(f"\nreport: {md_path}")
    print(f"json  : {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
