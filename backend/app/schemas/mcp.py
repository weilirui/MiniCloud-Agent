"""MCP API schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MCPServerStatus(BaseModel):
    name: str
    command: str
    args: list[str]
    connected: bool
    description: str = ""
    tool_count: int = 0


class MCPServersResponse(BaseModel):
    servers: list[MCPServerStatus]
    total_tools: int


class MCPRestartResponse(BaseModel):
    name: str
    connected: bool
    message: str = "restarted"