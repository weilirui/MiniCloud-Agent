"""Online evaluation: agent trajectories and generation quality.

Unlike :mod:`eval.runner` (retrieval only, fully offline-capable), this runner
needs a real chat model, because the things it measures — did the agent pick
the right tool, is the answer grounded in the retrieved context — cannot be
faked.

Two suites
----------
``agent``
    Runs each task in ``datasets/agent_tasks.jsonl`` through the real Agent
    loop and scores tool selection, exact match, task success and step count.
``generation``
    Answers each golden query from retrieved context and scores how much of
    the answer is actually backed by that context (``lexical_support``) and
    whether it cites its sources (``citation_rate``).

Honest scope
------------
MCP tools (``mcp__filesystem__*``, ``mcp__fetch__*``) are *declared* to the
model but executed by a stub, because spinning up real MCP servers requires
npx and network installs. So tool-selection accuracy is meaningful, while
``task_success`` on MCP tasks only reflects whether the stub output was
echoed back, not whether a real file was read. Skills and RAG run for real.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any

# ``eval/__init__.py`` seeds OPENAI_API_KEY with a placeholder so offline runs
# do not crash on import. This suite talks to a real model, so the project
# .env has to win — and it must happen before app.config is imported.
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=True)

from app.core.agent import Agent, AgentDeps  # noqa: E402
from app.core.llm import LLMClient  # noqa: E402
from app.core.prompts import (  # noqa: E402
    build_mcp_tools_summary,
    build_skills_summary,
    build_system_prompt,
)
from app.rag.hybrid import HybridConfig, HybridRetriever  # noqa: E402
from app.skills.registry import SkillsRegistry  # noqa: E402
from eval.metrics.agent import evaluate_agent_traces  # noqa: E402
from eval.metrics.generation import evaluate_generation  # noqa: E402
from eval.runner import build_chunks, build_lexical_index, load_jsonl  # noqa: E402

DATASETS = Path(__file__).parent / "datasets"
REPORTS = Path(__file__).parent / "reports"

ANSWER_PROMPT = """你是 minicloud-agent 的问答助手。只能依据下面提供的材料回答问题，
不要引入材料之外的信息。引用来源时写成 [来源 N] 的形式，N 对应材料编号。

材料：
{context}

问题：
{question}

回答（简洁，不超过 120 字）："""


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------

class StubMCPManager:
    """Declares the MCP tools the eval expects without spawning subprocesses."""

    def __init__(self) -> None:
        self.tools = [
            {
                "name": "mcp__filesystem__read_file",
                "description": "读取指定路径的文件内容",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
                "server": "filesystem",
                "original_name": "read_file",
            },
            {
                "name": "mcp__filesystem__list_directory",
                "description": "列出目录下的文件",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
                "server": "filesystem",
                "original_name": "list_directory",
            },
            {
                "name": "mcp__fetch__fetch",
                "description": "抓取指定 URL 的页面内容",
                "parameters": {
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"],
                },
                "server": "fetch",
                "original_name": "fetch",
            },
        ]

    def list_tools(self) -> list[dict]:
        return self.tools

    async def call_tool(self, server: str, name: str, arguments: dict) -> str:
        return f"[stub] {server}.{name}({arguments})"


class EvalRetriever:
    """Hybrid retriever over the eval corpus, exposing the Agent-facing API."""

    def __init__(self, hybrid: HybridRetriever) -> None:
        self._hybrid = hybrid

    async def retrieve(self, query: str, top_k: int = 5, **_: Any) -> list[dict]:
        return await self._hybrid.retrieve(query, top_k=top_k)


def build_registry() -> SkillsRegistry:
    from app.config import settings

    registry = SkillsRegistry()
    registry.scan_directory(settings.skills_builtin_dir)
    if not registry.list():
        # Running from the host rather than inside the container.
        root = Path(__file__).resolve().parents[1]
        registry.scan_directory(root / "app" / "skills" / "builtin")
    return registry


# --------------------------------------------------------------------------
# suites
# --------------------------------------------------------------------------

async def run_agent_suite(llm: LLMClient, retriever: EvalRetriever, limit: int | None) -> dict:
    tasks = load_jsonl(DATASETS / "agent_tasks.jsonl")
    if limit:
        tasks = tasks[:limit]

    registry = build_registry()
    mcp = StubMCPManager()
    system_prompt = build_system_prompt(
        current_time=time.strftime("%Y-%m-%d %H:%M:%S"),
        os_info="eval",
        cwd=str(Path(__file__).resolve().parents[1]),
        skills_summary=build_skills_summary(
            [
                {
                    "name": s.name,
                    "description": s.description,
                    "trigger": getattr(s, "trigger", "") or f"/{s.name}",
                }
                for s in registry.list()
            ]
        ),
        mcp_tools_summary=build_mcp_tools_summary(mcp.list_tools()),
    )

    # Built-in skills (``rag_qa``) call ``get_retriever()`` themselves instead
    # of using the injected dependency, which would send them to the production
    # Qdrant collection — empty during eval, and in this environment behind a
    # dead embedding key. Point the singleton at the eval corpus instead.
    import app.rag.retriever as retriever_module

    retriever_module._retriever = retriever  # noqa: SLF001

    traces: list[dict] = []
    for task in tasks:
        agent = Agent(
            llm=llm,
            deps=AgentDeps(skills_registry=registry, mcp_manager=mcp, retriever=retriever),
            max_iterations=3,  # keep cost and latency bounded per task
        )
        tools: list[str] = []
        answer = ""
        try:
            async for event in agent.run(
                messages=[{"role": "user", "content": task["query"]}],
                system_prompt=system_prompt,
            ):
                if event.type == "tool_call_start":
                    tools.append(event.data.get("name", ""))
                elif event.type == "content":
                    answer += event.data.get("delta", "")
                elif event.type == "done" and event.data.get("content"):
                    answer += event.data["content"]
        except Exception as exc:
            answer += f"[error] {exc}"

        traces.append(
            {
                "task_id": task["task_id"],
                "tools": [t for t in tools if t],
                "final": answer,
                "expected_tools": task.get("expected_tools", []),
                "must_contain": task.get("must_contain", []),
            }
        )

    return {"traces": traces, "scores": evaluate_agent_traces(traces)}


async def run_generation_suite(
    llm: LLMClient, retriever: EvalRetriever, limit: int | None, top_k: int
) -> dict:
    golden_rows = load_jsonl(DATASETS / "golden_retrieval.jsonl")
    if limit:
        golden_rows = golden_rows[:limit]

    samples: list[dict] = []
    for row in golden_rows:
        query = row["query"]
        hits = await retriever.retrieve(query, top_k=top_k)
        contexts = [h.get("text", "") for h in hits]
        if not contexts:
            samples.append({"answer": "", "contexts": [], "query": query})
            continue

        context_block = "\n\n".join(f"[来源 {i}] {c}" for i, c in enumerate(contexts, start=1))
        try:
            resp = await llm.chat(
                messages=[
                    {
                        "role": "user",
                        "content": ANSWER_PROMPT.format(context=context_block, question=query),
                    }
                ],
                temperature=0.0,
            )
            answer = resp.content or ""
        except Exception as exc:
            answer = f"[error] {exc}"

        samples.append({"answer": answer, "contexts": contexts, "query": query})

    return {"samples": samples, "scores": evaluate_generation(samples)}


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------

def render_report(result: dict[str, Any]) -> str:
    lines = ["# 在线评测报告（Agent 轨迹 / 生成质量）", ""]
    meta = result["meta"]
    lines.append(f"- 生成时间：{meta['generated_at']}")
    lines.append(f"- 模型：`{meta['model']}`")
    lines.append(f"- 向量：`{meta['embedder']}`")
    lines.append("")

    if "agent" in result:
        scores = result["agent"]["scores"]
        lines.append("## Agent 轨迹")
        lines.append("")
        lines.append("| 指标 | 值 |")
        lines.append("|---|---|")
        for key in ("tasks", "tool_selection_acc", "tool_selection_exact", "avg_steps", "max_steps"):
            if key in scores:
                lines.append(f"| `{key}` | {scores[key]} |")
        if scores.get("task_success_rate") is not None:
            n = int(scores.get("task_success_n", 0))
            lines.append(f"| `task_success_rate` | {scores['task_success_rate']} （{n} 条声明了 must_contain） |")
        lines.append("")
        lines.append("| 任务 | 期望工具 | 实际工具 | 命中 |")
        lines.append("|---|---|---|---|")
        for trace in result["agent"]["traces"]:
            expected = ", ".join(trace["expected_tools"]) or "（无）"
            actual = ", ".join(trace["tools"]) or "（无）"
            ok = "✅" if set(trace["tools"]) == set(trace["expected_tools"]) else "❌"
            lines.append(f"| {trace['task_id']} | {expected} | {actual} | {ok} |")
        lines.append("")

    if "generation" in result:
        scores = result["generation"]["scores"]
        lines.append("## 生成质量")
        lines.append("")
        lines.append("| 指标 | 值 |")
        lines.append("|---|---|")
        for key in ("samples", "lexical_support", "citation_rate"):
            if key in scores:
                lines.append(f"| `{key}` | {scores[key]} |")
        lines.append("")

    lines.append("> 说明：MCP 工具在本次评测中只做声明、由 stub 执行（真实 MCP server 需要 npx 与联网安装）。")
    lines.append("> 因此 `tool_selection_acc` 有意义，而 MCP 任务上的 `task_success_rate` 只反映 stub 回显，不等于真实文件被读取。")
    lines.append("")
    return "\n".join(lines)


def write_reports(result: dict[str, Any]) -> tuple[Path, Path]:
    REPORTS.mkdir(parents=True, exist_ok=True)
    md_path = REPORTS / "online_eval_report.md"
    json_path = REPORTS / "online_eval_report.json"
    md_path.write_text(render_report(result), encoding="utf-8")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return md_path, json_path


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

async def run(suite: str, limit: int | None, top_k: int, embedder: str) -> dict[str, Any]:
    from eval.local_embedder import LocalEmbedder
    from eval.offline_embedder import HashingEmbedder
    from eval.stores.memory import InMemoryVectorStore

    embedding = LocalEmbedder() if embedder == "local" else HashingEmbedder()
    corpus = load_jsonl(DATASETS / "corpus.jsonl")
    chunks = build_chunks(corpus, 180, 40)
    store = InMemoryVectorStore(embedding)
    await store.add(chunks)

    retriever = EvalRetriever(
        HybridRetriever(
            vector_search=store.search,
            lexical_index=build_lexical_index(chunks),
            config=HybridConfig(enable_mmr=True),
        )
    )

    llm = LLMClient()
    result: dict[str, Any] = {
        "meta": {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "model": llm.model,
            "embedder": embedder,
            "top_k": top_k,
        }
    }

    if suite in ("agent", "all"):
        result["agent"] = await run_agent_suite(llm, retriever, limit)
    if suite in ("generation", "all"):
        result["generation"] = await run_generation_suite(llm, retriever, limit, top_k)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Online (LLM-backed) evaluation")
    parser.add_argument("--suite", choices=("agent", "generation", "all"), default="all")
    parser.add_argument("--limit", type=int, default=None, help="only run the first N items")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--embedder", choices=("offline", "local"), default="local")
    args = parser.parse_args()

    result = asyncio.run(run(args.suite, args.limit, args.top_k, args.embedder))
    md_path, json_path = write_reports(result)

    if "agent" in result:
        s = result["agent"]["scores"]
        print(f"agent      acc={s['tool_selection_acc']} exact={s['tool_selection_exact']} "
              f"success={s['task_success_rate']} avg_steps={s['avg_steps']}")
    if "generation" in result:
        s = result["generation"]["scores"]
        print(f"generation support={s['lexical_support']} citation={s['citation_rate']}")
    print(f"report: {md_path}")


if __name__ == "__main__":
    main()
