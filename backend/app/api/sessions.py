"""Sessions CRUD endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete as sa_delete, func as sa_func, select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Message, Session
from app.deps import get_db
from app.schemas.session import (
    MessageOut,
    SessionCreate,
    SessionDetail,
    SessionOut,
)

router = APIRouter()


@router.get("/")
async def list_sessions(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List sessions, most recent first."""
    count_q = sa_select(sa_func.count(Session.id))
    total = (await db.execute(count_q)).scalar() or 0

    q = sa_select(Session).order_by(Session.updated_at.desc()).limit(limit).offset(offset)
    rows = (await db.execute(q)).scalars().all()

    # get message counts
    msg_count_q = sa_select(Message.session_id, sa_func.count(Message.id)).group_by(Message.session_id)
    msg_counts = {
        sid: cnt for sid, cnt in (await db.execute(msg_count_q)).all()
    }

    items = [
        SessionOut(
            id=s.id,
            title=s.title,
            model=s.model,
            created_at=s.created_at,
            updated_at=s.updated_at,
            message_count=msg_counts.get(s.id, 0),
        )
        for s in rows
    ]
    return {"items": [i.model_dump(mode="json") for i in items], "total": total}


@router.post("/")
async def create_session(
    req: SessionCreate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a new session."""
    s = Session(
        title=req.title or "New Chat",
        model=req.model or "gpt-4o-mini",
        system_prompt=req.system_prompt,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return SessionOut(
        id=s.id,
        title=s.title,
        model=s.model,
        created_at=s.created_at,
        updated_at=s.updated_at,
        message_count=0,
    ).model_dump(mode="json")


@router.get("/{session_id}")
async def get_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get a session with all messages."""
    s = (await db.execute(sa_select(Session).where(Session.id == session_id))).scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="session not found")

    msgs = (
        await db.execute(
            sa_select(Message).where(Message.session_id == session_id).order_by(Message.created_at.asc())
        )
    ).scalars().all()

    detail = SessionDetail(
        id=s.id,
        title=s.title,
        model=s.model,
        created_at=s.created_at,
        updated_at=s.updated_at,
        message_count=len(msgs),
        system_prompt=s.system_prompt,
        messages=[
            MessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                tool_calls=m.tool_calls,
                tool_call_id=m.tool_call_id,
                name=m.name,
                created_at=m.created_at,
            )
            for m in msgs
        ],
    )
    return detail.model_dump(mode="json")


@router.delete("/{session_id}")
async def delete_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete a session (and its messages)."""
    result = await db.execute(sa_delete(Session).where(Session.id == session_id))
    await db.commit()
    return {"deleted": result.rowcount or 0}


@router.patch("/{session_id}")
async def update_session(
    session_id: UUID,
    req: SessionCreate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update session title/model/system_prompt."""
    s = (await db.execute(sa_select(Session).where(Session.id == session_id))).scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="session not found")

    if req.title is not None:
        s.title = req.title
    if req.model is not None:
        s.model = req.model
    if req.system_prompt is not None:
        s.system_prompt = req.system_prompt

    await db.commit()
    await db.refresh(s)
    return SessionOut(
        id=s.id,
        title=s.title,
        model=s.model,
        created_at=s.created_at,
        updated_at=s.updated_at,
        message_count=0,
    ).model_dump(mode="json")