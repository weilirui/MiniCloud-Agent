"""Feedback endpoints: collect bad cases and expose aggregate quality stats."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func as sa_func, select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.feedback.service import FeedbackService
from app.schemas.feedback import FeedbackCreate, FeedbackOut, FeedbackStats
from app.utils.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)

NEGATIVE_THRESHOLD = 4


def _db_sink(db: AsyncSession):
    """Persist one feedback record into ``message_feedback``."""

    async def sink(record) -> None:
        from uuid import UUID

        from app.db.models import MessageFeedback

        def as_uuid(value):
            try:
                return UUID(str(value)) if value else None
            except (ValueError, AttributeError):
                return None

        db.add(
            MessageFeedback(
                session_id=as_uuid(record.session_id),
                message_id=as_uuid(record.message_id),
                rating=record.rating,
                query=record.query or None,
                answer=record.answer or None,
                comment=record.comment or None,
                tags=list(record.tags or []),
            )
        )
        await db.commit()

    return sink


@router.post("/", response_model=FeedbackOut)
async def submit_feedback(
    req: FeedbackCreate,
    db: AsyncSession = Depends(get_db),
) -> FeedbackOut:
    """Record a rating for one answer. Ratings below 4 become labelled bad cases."""
    service = FeedbackService(sink=_db_sink(db))
    record = await service.submit(
        session_id=str(req.session_id) if req.session_id else "",
        rating=req.rating,
        message_id=str(req.message_id) if req.message_id else None,
        query=req.query or "",
        answer=req.answer or "",
        comment=req.comment or "",
        tags=req.tags,
    )
    logger.info("feedback_endpoint_called", rating=record.rating)
    return FeedbackOut(
        session_id=record.session_id or None,
        message_id=record.message_id,
        rating=record.rating,
        label="bad" if record.is_negative else "good",
    )


@router.get("/stats", response_model=FeedbackStats)
async def feedback_stats(db: AsyncSession = Depends(get_db)) -> FeedbackStats:
    """Aggregate quality signal across all collected feedback."""
    from app.db.models import MessageFeedback

    row = (
        await db.execute(
            sa_select(
                sa_func.count(MessageFeedback.id),
                sa_func.avg(MessageFeedback.rating),
            )
        )
    ).one()
    total = int(row[0] or 0)
    avg_rating = float(row[1] or 0.0)

    negative = 0
    if total:
        negative = int(
            (
                await db.execute(
                    sa_select(sa_func.count(MessageFeedback.id)).where(
                        MessageFeedback.rating < NEGATIVE_THRESHOLD
                    )
                )
            ).scalar()
            or 0
        )

    return FeedbackStats(
        total=total,
        negative=negative,
        negative_rate=round(negative / total, 4) if total else 0.0,
        avg_rating=round(avg_rating, 3),
    )
