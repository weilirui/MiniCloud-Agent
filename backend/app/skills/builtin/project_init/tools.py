"""Project init skill — 扫描项目并生成说明书."""

from __future__ import annotations

import os
from pathlib import Path

from app.skills.base import Skill, SkillContext
from app.utils.logging import get_logger

logger = get_logger(__name__)

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
             ".next", ".vite", ".idea", ".vscode", "data", ".workbuddy"}
MAX_DEPTH = 4
MAX_TREE_LINES = 200


def build_tree(root: Path, depth: int = 0, max_depth: int = MAX_DEPTH) -> list[str]:
    lines: list[str] = []
    if depth > max_depth:
        return lines
    try:
        entries = sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except (PermissionError, FileNotFoundError):
        return lines
    for e in entries:
        if e.name in SKIP_DIRS or e.name.startswith("."):
            if e.name not in (".env.example", ".gitignore"):
                continue
        prefix = "  " * depth + ("├── " if depth > 0 else "")
        if e.is_dir():
            lines.append(f"{prefix}{e.name}/")
            lines.extend(build_tree(e, depth + 1, max_depth))
        else:
            lines.append(f"{prefix}{e.name}")
    return lines[:MAX_TREE_LINES]


class ProjectInitSkill(Skill):
    name = "project_init"
    description = "扫描当前项目结构，生成项目说明书（类似 CLAUDE.md）"
    trigger = "/init"
    parameters = {"type": "object", "properties": {}, "required": []}

    async def invoke(self, ctx: SkillContext, **kwargs) -> str:
        cwd = Path(os.getcwd())
        tree = build_tree(cwd)

        # Detect stack
        stack = []
        if (cwd / "pyproject.toml").exists():
            stack.append("Python (pyproject.toml)")
        if (cwd / "package.json").exists():
            stack.append("Node.js (package.json)")
        if (cwd / "Cargo.toml").exists():
            stack.append("Rust")
        if (cwd / "go.mod").exists():
            stack.append("Go")
        if (cwd / "docker-compose.yml").exists():
            stack.append("Docker Compose")

        prompt = (
            f"根据以下信息生成项目说明书（Markdown 格式），包含：项目简介、技术栈、目录结构、常用命令。\n\n"
            f"技术栈: {', '.join(stack) or '未知'}\n\n"
            f"目录结构:\n```\n{chr(10).join(tree)}\n```\n\n"
            "请直接输出 Markdown 内容，不要任何额外说明。"
        )

        resp = await ctx.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1500,
        )
        return resp.content or "（生成失败）"