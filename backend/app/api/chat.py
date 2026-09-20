"""Chat endpoints: SSE streaming + non-streaming."""

from __future__ import annotations

import os
import platform
from collections.abc import AsyncGenerator
from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.agent import Agent, AgentDeps
from app.core.prompts import build_system_prompt
from app.db.models import Message, Session, ToolInvocation
from app.deps import get_db
from app.mcp.manager import get_manager
from app.rag.retriever import get_retriever
from app.schemas.chat import ChatRequest
from app.skills.registry import get_registry
from app.utils.errors import SessionNotFound
from app.utils.logging import get_logger
from app.utils.streaming import sse_pack

router = APIRouter()
logger = get_logger(__name__)


def _system_prompt() -> str:
    return build_system_prompt(
        current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        os_info=f"{platform.system()} {platform.release()}",
        cwd=os.getcwd(),
    )


async def _get_or_create_session(
    db: AsyncSession, session_id: UUID | None, default_model: str | None
) -> Session:
    if session_id:
        result = await db.execute(sa_select(Session).where(Session.id == session_id))
        s = result.scalar_one_or_none()
        if s:
            return s
        raise SessionNotFound(f"session not found: {session_id}")
    s = Session(
        id=uuid4(),
        title="New Chat",
        model=default_model or settings.openai_model,
        system_prompt=None,
    )
    db.add(s)
    await db.flush()
    return s


async def _load_history(db: AsyncSession, session_id: UUID) -> list[dict]:
    """Load last N messages for the session."""
    result = await db.execute(
        sa_select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
        .limit(50)
    )
    rows = result.scalars().all()
    out = []
    for m in rows:
        msg: dict = {"role": m.role, "content": m.content or ""}
        if m.tool_calls:
            msg["tool_calls"] = m.tool_calls
            # An assistant turn that only requests tools has no text; keep it
            # null so the provider receives a well-formed tool_calls message.
            if not m.content:
                msg["content"] = None
        if m.tool_call_id:
            msg["tool_call_id"] = m.tool_call_id
        if m.name:
            msg["name"] = m.name
        out.append(msg)
    return out


async def _save_message(
    db: AsyncSession,
    session_id: UUID,
    role: str,
    content: str | None,
    tool_calls: list[dict] | None = None,
    tool_call_id: str | None = None,
    name: str | None = None,
) -> Message:
    msg = Message(
        session_id=session_id,
        role=role,
        content=content,
        tool_calls=tool_calls,
        tool_call_id=tool_call_id,
        name=name,
    )
    db.add(msg)
    await db.flush()
    return msg


async def _save_tool_invocation(
    db: AsyncSession,
    session_id: UUID,
    source: str,
    name: str,
    arguments: dict,
    result: str,
    status: str,
    duration_ms: int,
    error: str | None,
    message_id: UUID | None = None,
) -> None:
    inv = ToolInvocation(
        session_id=session_id,
        message_id=message_id,
        source=source,
        name=name,
        arguments=arguments,
        result=result,
        status=status,
        duration_ms=duration_ms,
        error=error,
    )
    db.add(inv)
    await db.flush()


def _build_agent(session_id: UUID, db: AsyncSession) -> Agent:
    """Build an Agent wired with all dependencies."""

    async def save_msg(
        role: str,
        content: str | None,
        tool_calls: list[dict] | None = None,
        tool_call_id: str | None = None,
        name: str | None = None,
        **_,
    ):
        await _save_message(
            db,
            session_id,
            role,
            content,
            tool_calls=tool_calls,
            tool_call_id=tool_call_id,
            name=name,
        )

    async def save_inv(**kwargs):
        kwargs.pop("session_id", None)  # agent passes it in kwargs too; closure value is authoritative
        await _save_tool_invocation(db, session_id, **kwargs)

    deps = AgentDeps(
        skills_registry=get_registry(),
        mcp_manager=get_manager(),
        retriever=get_retriever(),
        session_id=session_id,
        save_message=save_msg,
        save_tool_invocation=save_inv,
    )
    return Agent(deps=deps)


@router.post("/stream")
async def chat_stream(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream chat completion as SSE.

    Events:
      - content: {"delta": "..."}
      - tool_call_start: {"id", "name", "arguments"}
      - tool_call_result: {"tool_call_id", "name", "content", "status", "duration_ms"}
      - done: {"finish_reason", "content"}
      - error: {"message"}
    """
    session = await _get_or_create_session(db, req.session_id, req.model)
    session_id = session.id

    # Persist user message
    await _save_message(db, session_id, "user", req.message)
    await db.commit()

    history = await _load_history(db, session_id)
    sys_prompt = session.system_prompt or _system_prompt()

    agent = _build_agent(session_id, db)

    async def event_gen() -> AsyncGenerator[str, None]:
        try:
            yield sse_pack("start", {"session_id": str(session_id)})

            async for ev in agent.run(messages=history, system_prompt=sys_prompt):
                ev_type = ev.type
                if ev_type == "content":
                    yield sse_pack("content", {"delta": ev.data.get("delta", "")})
                elif ev_type == "tool_call_start":
                    yield sse_pack("tool_call_start", {
                    "id": ev.data.get("id"),
                    "name": ev.data.get("name"),
                    "arguments": ev.data.get("arguments"),
                    })
                elif ev_type == "tool_call_result":
                    yield sse_pack("tool_call_result", ev.data)
                elif ev_type == "done":
                    yield sse_pack("done", {
                        "finish_reason": ev.data.get("finish_reason"),
                        "content": ev.data.get("content", ""),
                    })
                elif ev_type == "agent_iter_start":
                    yield sse_pack("iteration", {"n": ev.data.get("iteration")})
                elif ev_type == "error":
                    yield sse_pack("error", ev.data)
        except Exception as e:
            logger.exception("chat_stream_failed")
            yield sse_pack("error", {"message": str(e)})
        finally:
            try:
                await db.commit()
            except Exception:
                pass

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/completions")
async def chat_completions(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Non-streaming chat completion."""
    session = await _get_or_create_session(db, req.session_id, req.model)
    session_id = session.id

    await _save_message(db, session_id, "user", req.message)
    await db.commit()

    history = await _load_history(db, session_id)
    sys_prompt = session.system_prompt or _system_prompt()

    agent = _build_agent(session_id, db)

    final_content = ""
    tool_calls_log: list[dict] = []
    finish_reason = "stop"

    async for ev in agent.run(messages=history, system_prompt=sys_prompt):
        if ev.type == "content":
            final_content += ev.data.get("delta", "")
        elif ev.type == "tool_call_start":
            tool_calls_log.append({
                "id": ev.data.get("id"),
                "name": ev.data.get("name"),
                "arguments": ev.data.get("arguments"),
            })
        elif ev.type == "done":
            finish_reason = ev.data.get("finish_reason", "stop")

    await db.commit()

    return {
        "session_id": str(session_id),
        "content": final_content,
        "finish_reason": finish_reason,
        "tool_calls": tool_calls_log,
    }