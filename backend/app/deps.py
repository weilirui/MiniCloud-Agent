"""FastAPI dependency injection factories."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a DB session."""
    factory = get_session_factory()
    async with factory() as session:
        yield session