"""Web search skill — 调用 Tavily API 搜索."""

from __future__ import annotations

import os

import httpx

from app.skills.base import Skill, SkillContext
from app.utils.logging import get_logger

logger = get_logger(__name__)


class WebSearchSkill(Skill):
    name = "web_search"
    description = "联网搜索最新信息"
    trigger = "/search"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
        },
        "required": ["query"],
    }

    async def invoke(self, ctx: SkillContext, query: str) -> str:
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            return "❌ 未配置 TAVILY_API_KEY，无法联网搜索。"

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": api_key,
                        "query": query,
                        "max_results": 5,
                        "search_depth": "basic",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            return f"❌ 搜索失败: {e}"

        results = data.get("results") or []
        if not results:
            return f"（未找到 `{query}` 的相关结果）"

        formatted = []
        for i, r in enumerate(results, 1):
            formatted.append(
                f"**[{i}] {r.get('title', '')}**\n"
                f"{r.get('content', '')[:400]}\n"
                f"🔗 {r.get('url', '')}"
            )

        context = "\n\n".join(formatted)
        summary = await ctx.llm.chat(
            messages=[{
                "role": "user",
                "content": f"基于以下搜索结果回答问题 `{query}`，中文，引用 [N]：\n\n{context}",
            }],
            temperature=0.4,
            max_tokens=1000,
        )

        return f"# Search: {query}\n\n{summary.content or ''}\n\n## 原始结果\n\n{context}"