"""Unit tests for the error hierarchy and FastAPI handlers."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.utils.errors import (
    LLMError,
    MCPServerError,
    MiniCloudError,
    RAGError,
    SessionNotFound,
    SkillNotFound,
    register_exception_handlers,
)


def test_base_error_defaults():
    err = MiniCloudError("boom")
    assert err.status_code == 500
    assert err.code == "internal_error"
    assert str(err) == "boom"


def test_error_accepts_overrides():
    err = MiniCloudError("nope", code="custom", status_code=418)
    assert err.code == "custom"
    assert err.status_code == 418


@pytest.mark.parametrize(
    "cls,status,code",
    [
        (SessionNotFound, 404, "session_not_found"),
        (SkillNotFound, 404, "skill_not_found"),
        (MCPServerError, 502, "mcp_server_error"),
        (RAGError, 500, "rag_error"),
        (LLMError, 502, "llm_error"),
    ],
)
def test_subclass_status_codes(cls, status, code):
    err = cls("x")
    assert err.status_code == status
    assert err.code == code
    assert isinstance(err, MiniCloudError)


def test_handler_returns_structured_error():
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom():
        raise SessionNotFound("session not found: 42")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/boom")

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "session_not_found"
    assert "42" in resp.json()["error"]["message"]


def test_handler_catches_unexpected_errors():
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/explode")
    async def explode():
        raise RuntimeError("kaboom")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/explode")

    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "internal_error"
    assert "kaboom" in resp.json()["error"]["message"]
