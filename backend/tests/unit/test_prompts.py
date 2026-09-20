"""Unit tests for system prompt assembly."""

from __future__ import annotations

from app.core.prompts import (
    MCP_TOOLS_SUMMARY_PLACEHOLDER,
    SKILLS_SUMMARY_PLACEHOLDER,
    build_mcp_tools_summary,
    build_skills_summary,
    build_system_prompt,
)


def test_build_system_prompt_fills_environment():
    prompt = build_system_prompt(
        current_time="2026-09-20 10:00:00",
        os_info="Windows 11",
        cwd="D:/repo",
    )
    assert "2026-09-20 10:00:00" in prompt
    assert "Windows 11" in prompt
    assert "D:/repo" in prompt


def test_build_system_prompt_includes_summaries():
    prompt = build_system_prompt(
        current_time="t",
        os_info="o",
        cwd="c",
        skills_summary="- `/echo` —— 回显",
        mcp_tools_summary="- `mcp__fs__read` —— 读文件",
    )
    assert "`/echo`" in prompt
    assert "mcp__fs__read" in prompt


def test_build_system_prompt_defaults_to_placeholders():
    prompt = build_system_prompt(current_time="t", os_info="o", cwd="c")
    assert SKILLS_SUMMARY_PLACEHOLDER in prompt
    assert MCP_TOOLS_SUMMARY_PLACEHOLDER in prompt


def test_skills_summary_empty():
    assert build_skills_summary([]) == SKILLS_SUMMARY_PLACEHOLDER


def test_skills_summary_uses_trigger():
    out = build_skills_summary([{"name": "echo", "description": "回显"}])
    assert "`/echo`" in out
    assert "回显" in out


def test_mcp_summary_empty():
    assert build_mcp_tools_summary([]) == MCP_TOOLS_SUMMARY_PLACEHOLDER


def test_mcp_summary_prefixes_server_name():
    out = build_mcp_tools_summary(
        [{"server": "filesystem", "name": "read_file", "description": "读文件"}]
    )
    assert "mcp__filesystem__read_file" in out
