"""Feedback collection: thumbs up/down -> annotated training candidates.

The point of this module is the loop it closes:
    bad answer -> structured record -> export -> annotation -> fine-tuning data
without it, every "这个回答不对" is lost the moment the page is refreshed.
"""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.utils.logging import get_logger

logger = get_logger(__name__)

POSITIVE_THRESHOLD = 4  # ratings >= 4 are positive on a 1..5 scale


@dataclass
class FeedbackRecord:
    """One piece of user feedback on one assistant answer."""

    session_id: str
    message_id: str | None
    rating: int
    query: str = ""
    answer: str = ""
    comment: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    @property
    def is_negative(self) -> bool:
        return self.rating < POSITIVE_THRESHOLD

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["is_negative"] = self.is_negative
        return data


class FeedbackService:
    """Collect feedback and export annotated candidates for training."""

    def __init__(
        self,
        sink: Callable[[FeedbackRecord], Awaitable[None]] | None = None,
        export_dir: str | Path | None = None,
    ) -> None:
        self.sink = sink
        self.export_dir = Path(export_dir) if export_dir else None
        self._records: list[FeedbackRecord] = []

    async def submit(
        self,
        session_id: str,
        rating: int,
        *,
        message_id: str | None = None,
        query: str = "",
        answer: str = "",
        comment: str = "",
        tags: list[str] | None = None,
    ) -> FeedbackRecord:
        """Record one feedback entry and forward it to the sink (if any)."""
        if not isinstance(rating, int) or not 1 <= rating <= 5:
            raise ValueError("rating must be an int in 1..5")

        rec = FeedbackRecord(
            session_id=str(session_id),
            message_id=str(message_id) if message_id else None,
            rating=rating,
            query=query,
            answer=answer,
            comment=comment,
            tags=list(tags or []),
        )
        self._records.append(rec)
        logger.info("feedback_recorded", session_id=rec.session_id, rating=rating)

        if self.sink is not None:
            try:
                await self.sink(rec)
            except Exception as exc:  # telemetry must not break the request
                logger.warning("feedback_sink_failed", error=str(exc))
        return rec

    # ---------- query ----------

    def all(self) -> list[FeedbackRecord]:
        return list(self._records)

    def negative(self) -> list[FeedbackRecord]:
        return [r for r in self._records if r.is_negative]

    def stats(self) -> dict[str, float]:
        total = len(self._records)
        if not total:
            return {"total": 0, "negative": 0, "negative_rate": 0.0, "avg_rating": 0.0}
        neg = len(self.negative())
        return {
            "total": float(total),
            "negative": float(neg),
            "negative_rate": round(neg / total, 4),
            "avg_rating": round(sum(r.rating for r in self._records) / total, 3),
        }

    # ---------- export ----------

    def export_jsonl(self, path: str | Path | None = None) -> Path:
        """Export feedback as JSONL annotation candidates.

        Each line: {"query", "answer", "rating", "tags", "comment", "label"}
        ``label`` is "bad" for negative feedback, "good" otherwise - the starting
        point for a human annotation pass.
        """
        target = Path(path) if path else (self.export_dir or Path("data/annotations")) / "feedback.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)

        with target.open("w", encoding="utf-8") as fh:
            for rec in self._records:
                fh.write(
                    json.dumps(
                        {
                            "session_id": rec.session_id,
                            "message_id": rec.message_id,
                            "query": rec.query,
                            "answer": rec.answer,
                            "rating": rec.rating,
                            "tags": rec.tags,
                            "comment": rec.comment,
                            "label": "bad" if rec.is_negative else "good",
                            "created_at": rec.created_at,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        logger.info("feedback_exported", path=str(target), count=len(self._records))
        return target
