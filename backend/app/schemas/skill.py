"""Skills API schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SkillInfo(BaseModel):
    name: str
    description: str
    trigger: str | None = None
    parameters: dict = Field(default_factory=dict)
    source: str = "builtin"  # builtin / user


class SkillInvokeRequest(BaseModel):
    name: str
    arguments: dict = Field(default_factory=dict)


class SkillInvokeResponse(BaseModel):
    name: str
    result: str