"""RAG Q&A skill — 从知识库检索并回答."""

from __future__ import annotations

from app.skills.base import Skill, SkillContext
from app.utils.logging import get_logger

logger = get_logger(__name__)


class RagQaSkill(Skill):
    name = "rag_qa"
    description = "从已上传的知识库检索并回答"
    trigger = "/rag"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "检索问题"},
            "top_k": {"type": "integer", "description": "检索条数", "default": 5},
        },
        "required": ["query"],
    }

    async def invoke(self, ctx: SkillContext, query: str, top_k: int = 5) -> str:
        from app.rag.retriever import get_retriever
        retriever = get_retriever()
        try:
            results = await retriever.retrieve(query, top_k=top_k, score_threshold=0.4)
        except Exception as e:
            return f"❌ 检索失败: {e}"

        if not results:
            return "（知识库未找到相关内容，请先在「知识库」页面上传文档。）"

        context = "\n\n".join(
            f"[来源 {i+1}] (score={r['score']:.2f})\n{r['text']}"
            for i, r in enumerate(results)
        )

        prompt = (
            "你是知识库问答助手。请基于以下检索结果回答用户问题，引用时标注 [来源 N]。"
            "如果检索结果不足，请明确说明。\n\n"
            f"## 用户问题\n{query}\n\n"
            f"## 检索结果\n{context}"
        )

        resp = await ctx.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1500,
        )
        return resp.content or "（生成失败）"