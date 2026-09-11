"""Git status skill — 查看 git 状态."""

from __future__ import annotations

import asyncio
import os

from app.skills.base import Skill, SkillContext
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def _run(cmd: str) -> str:
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        return f"(error) {stderr.decode().strip()}"
    return stdout.decode().strip()


class GitStatusSkill(Skill):
    name = "git_status"
    description = "查看 git 状态 + 最近提交 + 总结当前分支变化"
    trigger = "/git"
    parameters = {
        "type": "object",
        "properties": {
            "detail": {"type": "boolean", "description": "是否包含详细 diff", "default": False},
        },
        "required": [],
    }

    async def invoke(self, ctx: SkillContext, detail: bool = False) -> str:
        if not os.path.isdir(".git"):
            return "❌ 当前目录不是 git 仓库"

        branch = await _run("git branch --show-current")
        status = await _run("git status --short")
        log = await _run("git log --oneline -10")
        stat = await _run("git diff --stat HEAD")
        diff = ""
        if detail:
            diff = "\n\n## Diff\n```\n" + (await _run("git diff HEAD"))[:10000] + "\n```"

        summary_input = (
            f"## 分支\n{branch}\n\n"
            f"## 状态\n{status or '(clean)'}\n\n"
            f"## 最近提交\n{log}\n\n"
            f"## 变更统计\n{stat or '(无)'}"
        )

        resp = await ctx.llm.chat(
            messages=[{
                "role": "user",
                "content": f"总结当前 git 状态（中文，3-5 行）：\n\n{summary_input}",
            }],
            temperature=0.3,
            max_tokens=500,
        )

        out = f"# Git Status\n\n**分支**: `{branch}`\n\n"
        out += resp.content or ""
        out += f"\n\n<details><summary>原始状态</summary>\n\n```\n{summary_input}\n```\n\n</details>"
        out += diff
        return out