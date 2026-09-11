"""Async SQLAlchemy engine + sessionmaker."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Global engine, initialized at app startup
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Lazy-create async engine."""
    global _engine
    if _engine is None:
        logger.info("creating_db_engine", url=split_url(settings.database_url))
        _engine = create_async_engine(
            settings.database_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            echo=False,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Lazy-create session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _session_factory


async def init_db() -> None:
    """Initialize DB connection (verify reachability)."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
    logger.info("db_initialized")


async def close_db() -> None:
    """Close the engine."""
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("db_closed")


def split_url(url: str) -> str:
    """Hide password in URL for logging."""
    if "@" not in url:
        return url
    head, tail = url.split("@", 1)
    if ":" in head:
        scheme_user, _ = head.rsplit(":", 1)
        return f"{scheme_user}:***@{tail}"
    return url