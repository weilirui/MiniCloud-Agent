"""End-to-end smoke tests over the HTTP layer.

Intentionally built as a bare FastAPI app with only the routers under test:
the production ``create_app()`` lifespan spawns MCP subprocesses and connects
to PostgreSQL / Qdrant, which has no place in a fast smoke test.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import health, skills


@pytest.fixture
def client():
    app = FastAPI(title="minicloud-smoke")
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(skills.router, prefix="/api/v1/skills")
    with TestClient(app) as c:
        yield c


def test_health_endpoint(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_openapi_schema_is_served(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    assert "/api/v1/skills/" in resp.json()["paths"]


def test_list_skills(client):
    resp = client.get("/api/v1/skills/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] >= 6
    names = {item["name"] for item in body["items"]}
    assert {"echo", "code_review", "rag_qa"} <= names


def test_get_skill_by_name(client):
    resp = client.get("/api/v1/skills/echo")
    assert resp.status_code == 200
    assert resp.json()["trigger"] == "/echo"


def test_get_unknown_skill_returns_404(client):
    assert client.get("/api/v1/skills/definitely_not_here").status_code == 404


def test_invoke_echo_skill(client):
    resp = client.post(
        "/api/v1/skills/invoke", json={"name": "echo", "arguments": {"text": "ping"}}
    )
    assert resp.status_code == 200
    assert "ping" in resp.json()["result"]


def test_invoke_unknown_skill_returns_404(client):
    resp = client.post(
        "/api/v1/skills/invoke", json={"name": "nope", "arguments": {}}
    )
    assert resp.status_code == 404
