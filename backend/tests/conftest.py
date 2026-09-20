"""Shared pytest configuration and fixtures.

Two things happen here that are easy to get wrong:

1. ``app.config`` instantiates ``Settings()`` at import time and
   ``openai_api_key`` is a required field, so the environment must be primed
   *before* any ``app.*`` module is imported.
2. ``backend/`` must be on ``sys.path`` so ``import app`` works no matter
   whether pytest is started from the repo root or from ``backend/``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# ---- prime the environment before importing app.* ----
os.environ.setdefault("OPENAI_API_KEY", "test-key-not-used")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:1/v1")
os.environ.setdefault("OPENAI_MODEL", "gpt-4o-mini")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("QDRANT_URL", "http://localhost:16333")
os.environ.setdefault("SKILLS_BUILTIN_DIR", str(BACKEND_DIR / "app" / "skills" / "builtin"))
os.environ.setdefault("SKILLS_USER_DIR", str(REPO_ROOT / "data" / "skills"))
os.environ.setdefault("MCP_SERVERS_FILE", str(BACKEND_DIR / "mcp.servers.json"))


# --------------------------------------------------------------------------
# CLI flags
# --------------------------------------------------------------------------

def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="run tests that need a real PostgreSQL / Qdrant",
    )
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="run tests that call a real LLM API (costs money)",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "integration: requires PostgreSQL / Qdrant")
    config.addinivalue_line("markers", "live: calls a real LLM API")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip service-dependent tests unless explicitly asked for.

    Note: the check uses ``get_closest_marker``, not ``"integration" in
    item.keywords``. pytest puts *directory names* into ``item.keywords``, so a
    keyword check would silently skip everything under ``tests/integration/``
    - including tests that need no service at all.
    """
    skip_integration = pytest.mark.skip(
        reason="needs --run-integration and a reachable PostgreSQL / Qdrant"
    )
    skip_live = pytest.mark.skip(reason="needs --run-live (calls a real LLM API)")
    for item in items:
        if item.get_closest_marker("integration") and not config.getoption("--run-integration"):
            item.add_marker(skip_integration)
        if item.get_closest_marker("live") and not config.getoption("--run-live"):
            item.add_marker(skip_live)


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

@pytest.fixture
def backend_dir() -> Path:
    return BACKEND_DIR


@pytest.fixture
def builtin_skills_dir() -> Path:
    return BACKEND_DIR / "app" / "skills" / "builtin"


@pytest.fixture
def fake_llm():
    """A fresh FakeLLM. Tests push a script onto it via ``fake_llm.script``."""
    from tests.fakes.fake_llm import FakeLLM

    return FakeLLM()


@pytest.fixture
def skill_registry(builtin_skills_dir: Path):
    """Registry populated from the real builtin skills directory."""
    from app.skills.registry import SkillsRegistry

    registry = SkillsRegistry()
    registry.scan_directory(builtin_skills_dir)
    return registry


@pytest.fixture
def tmp_skill(tmp_path: Path) -> Path:
    """Write a throwaway skill (SKILL.md + tools.py) and return its directory."""
    skill_dir = tmp_path / "dummy_skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        """---
name: dummy
description: A dummy skill used by tests
trigger: "/dummy"
parameters:
  type: object
  properties:
    value:
      type: string
  required: ["value"]
---

# Dummy skill

Body of the dummy skill.
""",
        encoding="utf-8",
    )
    (skill_dir / "tools.py").write_text(
        '''"""Dummy skill implementation."""

from app.skills.base import Skill


class DummySkill(Skill):
    name = "dummy"
    description = "A dummy skill used by tests"
    trigger = "/dummy"

    async def invoke(self, ctx, **kwargs):
        return f"dummy:{kwargs.get('value', '')}"
''',
        encoding="utf-8",
    )
    return skill_dir
