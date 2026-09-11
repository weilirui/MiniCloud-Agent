"""Adapter: convert MCP tool format to Agent ToolSpec."""

from __future__ import annotations

from app.core.llm import ToolSpec


def mcp_tools_to_specs(tools: list[dict]) -> list[ToolSpec]:
    """Convert MCP manager list_tools() output to Agent ToolSpec list."""
    out: list[ToolSpec] = []
    for t in tools:
        out.append(ToolSpec(
            name=t["name"],  # already prefixed: mcp__<server>__<tool>
            description=t.get("description", ""),
            parameters=t.get("parameters", {"type": "object", "properties": {}}),
            source="mcp",
        ))
    return out