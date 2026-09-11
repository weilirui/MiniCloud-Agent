"""Memory abstractions: working (sliding window) + long-term (RAG-backed)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkingMemory:
    """In-memory working memory: a single session's recent messages.

    Provides a sliding window view and summarization hooks.
    """

    session_id: str
    system_prompt: str = ""
    messages: list[dict] = field(default_factory=list)
    summary: str = ""
    max_recent: int = 20

    def add_message(self, role: str, content: str, **extra: Any) -> None:
        msg = {"role": role, "content": content, **extra}
        self.messages.append(msg)

    def trim(self) -> None:
        """Trim messages to max_recent, preserving order."""
        if len(self.messages) > self.max_recent:
            self.messages = self.messages[-self.max_recent:]

    def to_messages(self) -> list[dict]:
        """Return messages for LLM consumption, prepending system + summary."""
        out = []
        if self.system_prompt:
            out.append({"role": "system", "content": self.system_prompt})
        if self.summary:
            out.append({
                "role": "system",
                "content": f"## 历史摘要\n\n{self.summary}",
            })
        out.extend(self.messages)
        return out

    def clear(self) -> None:
        self.messages.clear()
        self.summary = ""


@dataclass
class LongTermMemory:
    """Placeholder for long-term memory backed by RAG (Qdrant).

    The actual storage/retrieval happens via app.rag.retriever.
    """

    enabled: bool = True

    async def store(self, key: str, content: str, metadata: dict | None = None) -> None:
        """Store a memory entry. Implemented via rag.ingest."""
        # Concrete impl lives in services layer to avoid circular deps
        raise NotImplementedError("Wire up in service layer")

    async def retrieve(self, query: str, top_k: int = 5) -> list[dict]:
        """Retrieve memory entries relevant to query."""
        raise NotImplementedError("Wire up in service layer")