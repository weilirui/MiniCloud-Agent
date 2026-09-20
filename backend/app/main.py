"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, feedback, health, mcp, rag, sessions, skills
from app.config import settings
from app.db.session import close_db, init_db
from app.mcp.manager import get_manager, init_manager
from app.rag.qdrant_store import get_qdrant_store
from app.skills.registry import init_registry
from app.utils.errors import register_exception_handlers
from app.utils.logging import get_logger, setup_logging

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup/shutdown logic."""
    setup_logging(settings.log_level)
    logger.info("startup_begin", port=settings.app_port)

    # 1. Init DB
    try:
        await init_db()
    except Exception as e:
        logger.warning("db_init_failed", error=str(e))

    # 2. Ensure Qdrant collection
    try:
        store = get_qdrant_store()
        store.ensure_collection()
    except Exception as e:
        logger.warning("qdrant_init_failed", error=str(e))

    # 3. Load Skills registry
    try:
        registry = init_registry()
        logger.info("skills_loaded", count=len(registry.list()))
    except Exception as e:
        logger.warning("skills_init_failed", error=str(e))

    # 4. Start MCP servers (non-fatal)
    try:
        mgr = init_manager()
        await mgr.start_all()
    except Exception as e:
        logger.warning("mcp_init_failed", error=str(e))

    logger.info("startup_complete")
    yield

    # Shutdown
    logger.info("shutdown_begin")
    try:
        await get_manager().shutdown()
    except Exception:
        pass
    try:
        await close_db()
    except Exception:
        pass
    logger.info("shutdown_complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title="minicloud-agent",
        version="0.1.0",
        description="Mini Agent platform with RAG, Skills, MCP",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    app.include_router(health.router, prefix="/api/v1", tags=["health"])
    app.include_router(chat.router, prefix="/api/v1/chat", tags=["chat"])
    app.include_router(sessions.router, prefix="/api/v1/sessions", tags=["sessions"])
    app.include_router(rag.router, prefix="/api/v1/rag", tags=["rag"])
    app.include_router(skills.router, prefix="/api/v1/skills", tags=["skills"])
    app.include_router(mcp.router, prefix="/api/v1/mcp", tags=["mcp"])
    app.include_router(feedback.router, prefix="/api/v1/feedback", tags=["feedback"])

    return app


app = create_app()