"""Echo skill — 回显输入."""

from __future__ import annotations

from app.skills.base import Skill, SkillContext


class EchoSkill(Skill):
    name = "echo"
    description = "回显用户输入"
    trigger = "/echo"
    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "要回显的文本"},
        },
        "required": ["text"],
    }

    async def invoke(self, ctx: SkillContext, text: str) -> str:
        return f"🔁 Echo: {text}"