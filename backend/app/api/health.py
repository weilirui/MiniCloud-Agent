"""Health check endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.mcp.manager import get_manager
from app.rag.qdrant_store import get_qdrant_store
from app.db.session import get_engine

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    """Basic health check."""
    return {"status": "ok"}


@router.get("/health/full")
async def health_full() -> dict:
    """Full health check: DB + Qdrant + MCP."""
    checks: dict = {}

    # DB
    try:
        engine = get_engine()
        async with engine.begin() as conn:
            from sqlalchemy import text
            await conn.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"fail: {e}"

    # Qdrant
    try:
        store = get_qdrant_store()
        checks["qdrant"] = "ok" if store.health_check() else "fail"
        checks["qdrant_points"] = store.count()
    except Exception as e:
        checks["qdrant"] = f"fail: {e}"

    # MCP
    try:
        mgr = get_manager()
        servers = mgr.list_servers()
        checks["mcp_servers"] = servers
        checks["mcp_total_tools"] = sum(s.get("tool_count", 0) for s in servers)
    except Exception as e:
        checks["mcp"] = f"fail: {e}"

    status = "ok" if all(
        v == "ok" for v in checks.values() if isinstance(v, str)
    ) else "degraded"
    return {"status": status, "checks": checks}