"""Feedback API schemas."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class FeedbackCreate(BaseModel):
    """Thumbs up/down on one assistant answer."""

    session_id: UUID | None = None
    message_id: UUID | None = None
    rating: int = Field(ge=1, le=5, description="1..5, below 4 counts as a bad case")
    query: str | None = None
    answer: str | None = None
    comment: str | None = None
    tags: list[str] = Field(default_factory=list)


class FeedbackOut(BaseModel):
    session_id: str | None = None
    message_id: str | None = None
    rating: int
    label: str  # "bad" | "good"


class FeedbackStats(BaseModel):
    total: int = 0
    negative: int = 0
    negative_rate: float = 0.0
    avg_rating: float = 0.0
