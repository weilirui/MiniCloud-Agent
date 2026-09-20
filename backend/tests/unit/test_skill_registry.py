"""Unit tests for the Skills loader / registry."""

from __future__ import annotations

from pathlib import Path

from app.skills.registry import SkillsRegistry


def test_registry_loads_skill_with_implementation(tmp_skill: Path):
    registry = SkillsRegistry()
    registry.scan_directory(tmp_skill.parent)

    skill = registry.get("dummy")
    assert skill is not None
    assert skill.name == "dummy"
    assert skill.trigger == "/dummy"
    assert "dummy" in skill.description


async def test_skill_invocation_returns_expected_result(tmp_skill: Path):
    registry = SkillsRegistry()
    registry.scan_directory(tmp_skill.parent)
    skill = registry.get("dummy")

    result = await skill.invoke(None, value="42")
    assert result == "dummy:42"


def test_tool_schema_uses_skill_prefix(tmp_skill: Path):
    registry = SkillsRegistry()
    registry.scan_directory(tmp_skill.parent)
    schema = registry.get("dummy").get_tool_schema()

    assert schema["name"] == "skill_dummy"
    assert schema["parameters"]["type"] == "object"
    assert "value" in schema["parameters"]["properties"]


async def test_registry_falls_back_to_metadata_only_skill(tmp_path: Path):
    skill_dir = tmp_path / "no_impl"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        """---
name: no_impl
description: 没有实现的技能
trigger: "/no-impl"
---

只有正文，没有 tools.py。
""",
        encoding="utf-8",
    )

    registry = SkillsRegistry()
    registry.scan_directory(tmp_path)
    skill = registry.get("no_impl")
    assert skill is not None

    body = await skill.invoke(None)
    assert "只有正文" in body


def test_scan_missing_directory_is_a_noop(tmp_path: Path):
    registry = SkillsRegistry()
    registry.scan_directory(tmp_path / "does-not-exist")
    assert registry.list() == []


def test_register_requires_a_name():
    from app.skills.base import Skill

    class Nameless(Skill):
        async def invoke(self, ctx, **kwargs):
            return ""

    try:
        Nameless()
    except ValueError:
        return
    raise AssertionError("Skill without a name should be rejected")


def test_builtin_skills_are_discoverable(builtin_skills_dir: Path):
    registry = SkillsRegistry()
    registry.scan_directory(builtin_skills_dir)
    names = {s.name for s in registry.list()}
    for expected in ("echo", "project_init", "code_review", "rag_qa", "git_status", "web_search"):
        assert expected in names


async def test_builtin_echo_skill_roundtrip(builtin_skills_dir: Path):
    registry = SkillsRegistry()
    registry.scan_directory(builtin_skills_dir)
    echo = registry.get("echo")
    assert echo is not None

    result = await echo.invoke(None, text="ping")
    assert "ping" in result


def test_info_list_exposes_metadata(builtin_skills_dir: Path):
    registry = SkillsRegistry()
    registry.scan_directory(builtin_skills_dir)
    infos = registry.info_list()
    assert infos
    assert {"name", "description", "trigger", "parameters"} <= set(infos[0])
