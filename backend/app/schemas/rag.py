"""RAG API schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str
    top_k: int = 5
    score_threshold: float = 0.5
    filters: dict | None = None


class QueryHit(BaseModel):
    text: str
    source: str
    score: float
    metadata: dict = Field(default_factory=dict)


class QueryResponse(BaseModel):
    query: str
    hits: list[QueryHit]
    count: int


class DocOut(BaseModel):
    id: UUID
    filename: str
    source_type: str
    mime_type: str | None
    size_bytes: int | None
    chunk_count: int
    created_at: datetime


class UploadResponse(BaseModel):
    doc: DocOut
    message: str = "ingested"