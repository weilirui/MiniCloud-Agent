"""Chat API schemas."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: UUID | None = None
    message: str
    model: str | None = None
    temperature: float = 0.7
    stream: bool = True


class ToolCallInfo(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class MessageOut(BaseModel):
    id: UUID
    role: str
    content: str | None = None
    tool_calls: list[ToolCallInfo] | None = None
    tool_call_id: str | None = None
    name: str | None = None
    created_at: str


class ChatSSEEvent(BaseModel):
    """Schema doc only — actual events are dicts."""

    pass