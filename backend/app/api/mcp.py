"""MCP API: server status, restart, tool list."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.mcp.manager import get_manager
from app.schemas.mcp import MCPServersResponse, MCPServerStatus, MCPRestartResponse

router = APIRouter()


@router.get("/servers", response_model=MCPServersResponse)
async def list_servers() -> MCPServersResponse:
    """List all MCP servers and their status."""
    mgr = get_manager()
    servers = mgr.list_servers()
    total_tools = sum(s.get("tool_count", 0) for s in servers)
    return MCPServersResponse(
        servers=[
            MCPServerStatus(
                name=s["name"],
                command=s["command"],
                args=s.get("args", []),
                connected=s.get("connected", False),
                description=s.get("description", ""),
                tool_count=s.get("tool_count", 0),
            )
            for s in servers
        ],
        total_tools=total_tools,
    )


@router.post("/servers/{name}/restart", response_model=MCPRestartResponse)
async def restart_server(name: str) -> MCPRestartResponse:
    """Restart a specific MCP server."""
    mgr = get_manager()
    try:
        await mgr.restart(name)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return MCPRestartResponse(name=name, connected=True, message="restarted")


@router.get("/tools")
async def list_tools() -> dict:
    """List all tools available from MCP servers."""
    mgr = get_manager()
    tools = mgr.list_tools()
    return {"items": tools, "count": len(tools)}