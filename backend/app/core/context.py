"""Context window management.

Provides:
- Building the LLM input messages from working memory + system prompt
- Counting tokens and triggering summarization when over budget
"""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.utils.logging import get_logger
from app.utils.token_counter import count_message_tokens, count_tokens

logger = get_logger(__name__)


class ContextBuilder:
    """Manage context window: messages, system prompt, tools summary, RAG context."""

    def __init__(
        self,
        model: str = settings.openai_model,
        max_tokens: int = settings.max_context_tokens,
        max_recent_messages: int = 20,
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.max_recent_messages = max_recent_messages

    def build_messages(
        self,
        system_prompt: str,
        messages: list[dict],
        skills_summary: str = "",
        mcp_tools_summary: str = "",
        rag_context: list[dict] | None = None,
        summary: str = "",
    ) -> list[dict]:
        """Build the message list for the next LLM call.

        Strategy:
        - system_prompt with skills/mcp summaries appended
        - optional history summary (system role)
        - optional RAG context (system role)
        - last N messages from history
        """
        full_system = self._build_system_prompt(
            base=system_prompt,
            skills_summary=skills_summary,
            mcp_tools_summary=mcp_tools_summary,
            rag_context=rag_context,
        )

        out: list[dict] = [{"role": "system", "content": full_system}]
        if summary:
            out.append({"role": "system", "content": f"## 历史摘要\n\n{summary}"})
        # Take only last N
        recent = messages[-self.max_recent_messages:]
        out.extend(recent)
        return out

    def _build_system_prompt(
        self,
        base: str,
        skills_summary: str,
        mcp_tools_summary: str,
        rag_context: list[dict] | None,
    ) -> str:
        parts = [base]
        if skills_summary and skills_summary != "（暂无）":
            parts.append(f"\n## 可用 Skills\n{skills_summary}")
        if mcp_tools_summary and mcp_tools_summary != "（暂无）":
            parts.append(f"\n## 可用 MCP 工具\n{mcp_tools_summary}")
        if rag_context:
            ctx_text = "\n\n".join(
                f"[来源 {i+1}] {c.get('text', '')}" for i, c in enumerate(rag_context)
            )
            parts.append(f"\n## 知识库检索结果\n{ctx_text}\n\n如需引用，请在回答中标注 [来源 N]。")
        return "\n".join(parts)

    def estimate_tokens(self, messages: list[dict]) -> int:
        return count_message_tokens(messages, model=self.model)

    def should_summarize(self, messages: list[dict]) -> bool:
        return self.estimate_tokens(messages) > self.max_tokens

    def needs_trim(self, messages: list[dict]) -> bool:
        return len(messages) > self.max_recent_messages


async def summarize_messages(
    messages: list[dict],
    llm_client,
    *,
    model: str | None = None,
) -> str:
    """Summarize a list of messages using the LLM.

    Returns a concise summary string preserving key context (facts, decisions, file paths).
    """
    if not messages:
        return ""

    # Convert to text
    lines = []
    for m in messages:
        role = m.get("role", "")
        content = m.get("content") or ""
        if isinstance(content, list):
            content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
        lines.append(f"[{role}] {content[:500]}")

    text = "\n".join(lines)
    prompt = (
        "请将以下对话历史压缩为简洁的中文摘要，保留关键事实、决策、文件路径、用户偏好、"
        "未完成的任务。200 字以内。\n\n"
        f"{text}\n\n摘要："
    )

    try:
        resp = await llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=400,
        )
        return resp.content or ""
    except Exception as e:
        logger.warning("summarize_failed", error=str(e))
        # Fallback: truncate
        return text[:1000] + "..."