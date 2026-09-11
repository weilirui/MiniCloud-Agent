"""Code review skill — 用 LLM 审查指定文件."""

from __future__ import annotations

from pathlib import Path

from app.skills.base import Skill, SkillContext
from app.utils.logging import get_logger

logger = get_logger(__name__)


class CodeReviewSkill(Skill):
    name = "code_review"
    description = "对指定文件做代码审查，输出改进建议"
    trigger = "/code-review"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "要审查的文件路径（项目内相对路径）",
            },
        },
        "required": ["path"],
    }

    async def invoke(self, ctx: SkillContext, path: str) -> str:
        file_path = Path(path)
        if not file_path.exists():
            return f"❌ 文件不存在: {path}"

        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            return f"❌ 读取失败: {e}"

        if len(content) > 50_000:
            content = content[:50_000] + "\n\n...(truncated)"

        prompt = (
            f"请对以下代码文件 `{path}` 做一份结构化审查，输出：\n"
            "1. 总体评价（1-2 句）\n"
            "2. 优点（2-4 条）\n"
            "3. 问题（按严重程度排序，每条说明位置）\n"
            "4. 改进建议（含具体代码示例）\n\n"
            f"```\n{content}\n```"
        )

        resp = await ctx.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=2000,
        )
        return f"# Code Review: `{path}`\n\n{resp.content or '(empty)'}"