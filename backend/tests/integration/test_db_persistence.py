"""Integration tests against a real PostgreSQL.

Only run with ``pytest --run-integration``. If PostgreSQL is unreachable the
whole module skips instead of failing, so the default suite stays green on a
machine without Docker.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete as sa_delete, select as sa_select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.db.base import Base
from app.db.models import (
    LLMUsage,
    Message,
    MessageFeedback,
    Session,
    ToolInvocation,
)

pytestmark = pytest.mark.integration

TEST_TITLE_PREFIX = "[test]"


def _test_database_url():
    """The configured URL re-pointed at ``<db>_test``.

    These tests call ``Base.metadata.create_all``. Running that against the
    development database materializes tables that Alembic has not applied yet,
    so the next ``alembic upgrade head`` (i.e. the next container start) dies
    with ``DuplicateTableError``. A dedicated database keeps the two apart.
    """
    url = make_url(settings.database_url)
    if not url.database or url.database.endswith("_test"):
        return url
    return url.set(database=f"{url.database}_test")


async def _ensure_database(url) -> None:
    """Create the throwaway database if the server does not have it yet."""
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    admin = create_async_engine(
        url.set(database="postgres").render_as_string(hide_password=False),
        poolclass=NullPool,
        isolation_level="AUTOCOMMIT",  # CREATE DATABASE cannot run in a transaction
    )
    try:
        async with admin.connect() as conn:
            exists = (
                await conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :name"),
                    {"name": url.database},
                )
            ).scalar()
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    finally:
        await admin.dispose()


@pytest.fixture
async def db_engine():
    """A throwaway engine bound to this test's event loop.

    Do not use ``app.db.session.get_engine()`` here: it is a process-wide
    singleton whose pooled asyncpg connections stay attached to the loop that
    first opened them. pytest-asyncio hands every test a fresh loop, so the
    second test reuses a dead connection and dies with
    ``'NoneType' object has no attribute 'send'``. NullPool opens and closes
    connections inside the running loop instead.
    """
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    url = _test_database_url()
    try:
        await _ensure_database(url)
    except Exception as exc:
        pytest.skip(f"PostgreSQL 不可达: {exc}")

    engine = create_async_engine(
        url.render_as_string(hide_password=False), poolclass=NullPool, echo=False
    )
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"PostgreSQL 不可达: {exc}")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine
    await engine.dispose()


@pytest.fixture
async def db_factory(db_engine):
    factory = async_sessionmaker(bind=db_engine, expire_on_commit=False, class_=AsyncSession)
    yield factory

    async with factory() as db:
        await db.execute(sa_delete(Session).where(Session.title.like(f"{TEST_TITLE_PREFIX}%")))
        await db.execute(sa_delete(MessageFeedback).where(MessageFeedback.query.like(f"{TEST_TITLE_PREFIX}%")))
        await db.commit()


async def test_postgres_is_reachable(db_factory):
    async with db_factory() as db:
        value = (await db.execute(text("SELECT 1"))).scalar()
        assert value == 1


async def test_session_and_message_roundtrip(db_factory):
    async with db_factory() as db:
        session = Session(title=f"{TEST_TITLE_PREFIX} 会话", model="gpt-4o-mini")
        db.add(session)
        await db.flush()

        db.add(Message(session_id=session.id, role="user", content="第一个问题"))
        db.add(Message(session_id=session.id, role="assistant", content="第一个回答"))
        await db.commit()

        rows = (
            await db.execute(
                sa_select(Message)
                .where(Message.session_id == session.id)
                .order_by(Message.created_at.asc())
            )
        ).scalars().all()

        assert [m.content for m in rows] == ["第一个问题", "第一个回答"]
        assert [m.role for m in rows] == ["user", "assistant"]


async def test_deleting_session_cascades_to_messages(db_factory):
    async with db_factory() as db:
        session = Session(title=f"{TEST_TITLE_PREFIX} 级联删除")
        db.add(session)
        await db.flush()
        db.add(Message(session_id=session.id, role="user", content="会被删掉"))
        await db.commit()
        session_id = session.id

    async with db_factory() as db:
        await db.execute(sa_delete(Session).where(Session.id == session_id))
        await db.commit()
        remaining = (
            await db.execute(sa_select(Message).where(Message.session_id == session_id))
        ).scalars().all()

        assert remaining == []


async def test_tool_invocation_is_persisted(db_factory):
    async with db_factory() as db:
        session = Session(title=f"{TEST_TITLE_PREFIX} 工具审计")
        db.add(session)
        await db.flush()

        db.add(
            ToolInvocation(
                session_id=session.id,
                source="skill",
                name="skill_echo",
                arguments={"text": "hi"},
                result="Echo: hi",
                status="ok",
                duration_ms=12,
            )
        )
        await db.commit()

        rows = (
            await db.execute(sa_select(ToolInvocation).where(ToolInvocation.session_id == session.id))
        ).scalars().all()

        assert len(rows) == 1
        assert rows[0].source == "skill"
        assert rows[0].arguments == {"text": "hi"}
        assert rows[0].duration_ms == 12


async def test_failed_tool_invocation_records_error(db_factory):
    async with db_factory() as db:
        session = Session(title=f"{TEST_TITLE_PREFIX} 工具失败")
        db.add(session)
        await db.flush()

        db.add(
            ToolInvocation(
                session_id=session.id,
                source="mcp",
                name="mcp__fs__read",
                arguments={},
                result="Error: not connected",
                status="error",
                error="not connected",
            )
        )
        await db.commit()

        row = (
            await db.execute(sa_select(ToolInvocation).where(ToolInvocation.session_id == session.id))
        ).scalar_one()
        assert row.status == "error"
        assert row.error == "not connected"


async def test_llm_usage_persists(db_factory):
    async with db_factory() as db:
        session = Session(title=f"{TEST_TITLE_PREFIX} 成本记录")
        db.add(session)
        await db.flush()

        db.add(
            LLMUsage(
                session_id=session.id,
                model="gpt-4o-mini",
                endpoint="chat/stream",
                prompt_tokens=1200,
                completion_tokens=300,
                latency_ms=842,
                cost_usd=0.00036,
            )
        )
        await db.commit()

        row = (
            await db.execute(sa_select(LLMUsage).where(LLMUsage.session_id == session.id))
        ).scalar_one()
        assert row.model == "gpt-4o-mini"
        assert row.prompt_tokens == 1200
        assert row.latency_ms == 842


async def test_message_feedback_persists(db_factory):
    async with db_factory() as db:
        session = Session(title=f"{TEST_TITLE_PREFIX} 反馈")
        db.add(session)
        await db.flush()

        db.add(
            MessageFeedback(
                session_id=session.id,
                rating=2,
                query="RAG 的 top_k 是多少",
                answer="我不知道",
                comment="答错了",
                tags=["幻觉"],
            )
        )
        await db.commit()

        row = (
            await db.execute(sa_select(MessageFeedback).where(MessageFeedback.session_id == session.id))
        ).scalar_one()
        assert row.rating == 2
        assert row.tags == ["幻觉"]


def test_feedback_endpoint_persists_and_labels_bad_cases(db_factory):
    """The feedback loop only counts if it is reachable over HTTP."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import feedback as feedback_api
    from app.deps import get_db

    app = FastAPI()
    app.include_router(feedback_api.router, prefix="/api/v1/feedback")

    async def _override():
        async with db_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override
    client = TestClient(app)

    bad = client.post(
        "/api/v1/feedback/",
        json={
            "rating": 2,
            "query": f"{TEST_TITLE_PREFIX} RAG 的 top_k",
            "answer": "我不知道",
            "tags": ["幻觉"],
        },
    )
    assert bad.status_code == 200
    assert bad.json()["label"] == "bad"

    good = client.post(
        "/api/v1/feedback/",
        json={"rating": 5, "query": f"{TEST_TITLE_PREFIX} 部署端口", "answer": "16333"},
    )
    assert good.json()["label"] == "good"

    stats = client.get("/api/v1/feedback/stats")
    assert stats.status_code == 200
    body = stats.json()
    assert body["total"] >= 2
    assert body["negative"] >= 1
    assert 0.0 <= body["negative_rate"] <= 1.0


def test_feedback_endpoint_rejects_out_of_range_rating(db_factory):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import feedback as feedback_api
    from app.deps import get_db

    app = FastAPI()
    app.include_router(feedback_api.router, prefix="/api/v1/feedback")

    async def _override():
        async with db_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override

    assert TestClient(app).post("/api/v1/feedback/", json={"rating": 9}).status_code == 422


def test_sessions_api_creates_lists_and_deletes(db_factory):
    """Exercise the real HTTP layer against the real database."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import sessions as sessions_api
    from app.deps import get_db

    app = FastAPI()
    app.include_router(sessions_api.router, prefix="/api/v1/sessions")

    async def _override():
        async with db_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override
    client = TestClient(app)

    created = client.post(
        "/api/v1/sessions/", json={"title": f"{TEST_TITLE_PREFIX} api", "model": "gpt-4o-mini"}
    )
    assert created.status_code == 200
    session_id = created.json()["id"]

    listed = client.get("/api/v1/sessions/", params={"limit": 50})
    assert listed.status_code == 200
    assert any(item["id"] == session_id for item in listed.json()["items"])

    detail = client.get(f"/api/v1/sessions/{session_id}")
    assert detail.status_code == 200
    assert detail.json()["message_count"] == 0

    missing = client.get(f"/api/v1/sessions/{uuid.uuid4()}")
    assert missing.status_code == 404

    deleted = client.delete(f"/api/v1/sessions/{session_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] == 1


async def test_tool_trajectory_survives_storage_and_history_replay(db_factory):
    """The two halves of the tool-card fix, against a real PostgreSQL.

    1. ``_load_history`` must replay the provider shape (tool_calls + null
       content) so the model sees its own earlier tool calls.
    2. ``GET /sessions/{id}`` must hand the UI ``id / name / arguments``.
    """
    from app.api.chat import _load_history
    from app.api.sessions import get_session

    async with db_factory() as db:
        session = Session(title=f"{TEST_TITLE_PREFIX} 工具轨迹")
        db.add(session)
        await db.flush()

        db.add(
            Message(
                session_id=session.id,
                role="assistant",
                content=None,
                tool_calls=[
                    {
                        "id": "call_a",
                        "type": "function",
                        "function": {
                            "name": "rag_search",
                            "arguments": '{"query": "熔断器"}',
                        },
                    }
                ],
            )
        )
        db.add(
            Message(
                session_id=session.id,
                role="tool",
                content="命中 1 条",
                tool_call_id="call_a",
                name="rag_search",
            )
        )
        db.add(Message(session_id=session.id, role="assistant", content="熔断器在 core/retry.py"))
        await db.commit()

        history = await _load_history(db, session.id)
        tool_turn = next(m for m in history if m.get("tool_calls"))
        assert tool_turn["content"] is None
        assert tool_turn["tool_calls"][0]["function"]["name"] == "rag_search"
        result_turn = next(m for m in history if m["role"] == "tool")
        assert result_turn["tool_call_id"] == "call_a"
        assert result_turn["name"] == "rag_search"

        detail = await get_session(session.id, db)

    # Rows inserted in one transaction share a created_at, so assert on content
    # rather than on a positional order the database never promised.
    assert sorted(m["role"] for m in detail["messages"]) == ["assistant", "assistant", "tool"]
    cards = [m["tool_calls"] for m in detail["messages"] if m["tool_calls"]]
    assert cards == [[{"id": "call_a", "name": "rag_search", "arguments": {"query": "熔断器"}}]]
    result_row = next(m for m in detail["messages"] if m["role"] == "tool")
    assert result_row["tool_call_id"] == "call_a"
