"""Session API schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    title: str | None = None
    model: str | None = None
    system_prompt: str | None = None


class SessionOut(BaseModel):
    id: UUID
    title: str
    model: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class MessageOut(BaseModel):
    id: UUID
    role: str
    content: str | None
    tool_calls: list[dict] | None = None
    name: str | None = None
    tool_call_id: str | None = None
    created_at: datetime


class SessionDetail(SessionOut):
    system_prompt: str | None = None
    messages: list[MessageOut] = Field(default_factory=list)