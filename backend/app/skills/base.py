"""Skill base classes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.core.llm import LLMClient


@dataclass
class SkillContext:
    """Context provided to a skill when invoked.

    Gives access to LLM (for skills that need to call LLM),
    the current session id, and (future) RAG / MCP references.
    """

    llm: LLMClient
    session_id: str | None = None
    retriever: Any = None  # app.rag.retriever.Retriever (lazy import)
    extra: dict | None = None


class Skill(ABC):
    """Base class for a Skill.

    Subclass and implement invoke() to define behavior.
    The skill's name will be exposed to the LLM as `skill_<name>`.
    """

    name: str = ""
    description: str = ""
    trigger: str = ""  # e.g. "/code-review"
    parameters: dict = None  # type: ignore

    def __init__(self) -> None:
        if not self.name:
            raise ValueError("skill.name is required")
        if self.parameters is None:
            self.parameters = {
                "type": "object",
                "properties": {},
                "required": [],
            }

    def get_tool_schema(self) -> dict:
        """Return the tool spec for the LLM."""
        return {
            "name": f"skill_{self.name}",
            "description": self.description,
            "parameters": self.parameters,
        }

    @abstractmethod
    async def invoke(self, ctx: SkillContext, **kwargs: Any) -> str:
        """Execute the skill. Return a string result."""
        raise NotImplementedError

    def info(self) -> dict:
        """Public info for /api/v1/skills endpoint."""
        return {
            "name": self.name,
            "description": self.description,
            "trigger": self.trigger,
            "parameters": self.parameters,
        }