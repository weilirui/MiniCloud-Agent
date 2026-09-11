"""Custom exceptions and FastAPI exception handlers."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class MiniCloudError(Exception):
    """Base error for minicloud-agent."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class SessionNotFound(MiniCloudError):
    status_code = 404
    code = "session_not_found"


class SkillNotFound(MiniCloudError):
    status_code = 404
    code = "skill_not_found"


class MCPServerError(MiniCloudError):
    status_code = 502
    code = "mcp_server_error"


class RAGError(MiniCloudError):
    status_code = 500
    code = "rag_error"


class LLMError(MiniCloudError):
    status_code = 502
    code = "llm_error"


def register_exception_handlers(app: FastAPI) -> None:
    """Register handlers on the FastAPI app."""

    @app.exception_handler(MiniCloudError)
    async def handle_minicloud_error(request: Request, exc: MiniCloudError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": str(exc) or exc.__class__.__name__,
                }
            },
        )