"""MCP Manager: spawn and manage multiple MCP server connections."""

from __future__ import annotations

from typing import Any

from app.mcp.client import MCPClient
from app.mcp.config import MCPServerSpec, load_servers
from app.utils.errors import MCPServerError
from app.utils.logging import get_logger

logger = get_logger(__name__)


class MCPManager:
    """Manage a set of MCP server connections."""

    def __init__(self) -> None:
        self._clients: dict[str, MCPClient] = {}
        self._specs: dict[str, MCPServerSpec] = {}

    async def start_all(self, server_file: str | None = None) -> None:
        """Load configs and start all servers. Failed servers are logged but not fatal."""
        self._specs = load_servers(server_file)
        if not self._specs:
            logger.info("mcp_no_servers_configured")
            return

        for name, spec in self._specs.items():
            client = MCPClient(spec)
            try:
                await client.connect()
                self._clients[name] = client
            except Exception as e:
                logger.warning("mcp_server_start_failed", name=name, error=str(e))

        logger.info("mcp_started", ok=len(self._clients), total=len(self._specs))

    async def restart(self, name: str) -> None:
        if name not in self._specs:
            raise MCPServerError(f"unknown MCP server: {name}")
        # Close existing
        if name in self._clients:
            await self._clients[name].close()
            del self._clients[name]
        # Start fresh
        client = MCPClient(self._specs[name])
        await client.connect()
        self._clients[name] = client

    async def shutdown(self) -> None:
        for name, client in list(self._clients.items()):
            try:
                await client.close()
            except Exception as e:
                logger.warning("mcp_close_failed", name=name, error=str(e))
        self._clients.clear()

    def list_servers(self) -> list[dict]:
        return [
            {
                "name": name,
                "command": spec.command,
                "args": spec.args,
                "connected": self._clients.get(name, None) and self._clients[name].connected,
                "description": spec.description,
                "tool_count": len(self._clients.get(name, MCPClient(spec))._tools) if name in self._clients else 0,
            }
            for name, spec in self._specs.items()
        ]

    def list_tools(self) -> list[dict]:
        """List all tools from all connected servers.

        Tool names are prefixed with mcp__<server>__<tool>.
        """
        out: list[dict] = []
        for server_name, client in self._clients.items():
            for t in client._tools:
                out.append({
                    "name": f"mcp__{server_name}__{t['name']}",
                    "description": t.get("description", ""),
                    "parameters": t.get("parameters", {"type": "object", "properties": {}}),
                    "server": server_name,
                    "original_name": t["name"],
                })
        return out

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> str:
        client = self._clients.get(server_name)
        if not client or not client.connected:
            raise MCPServerError(f"MCP server not connected: {server_name}")
        return await client.call_tool(tool_name, arguments)


_manager: MCPManager | None = None


def init_manager() -> MCPManager:
    """Create the global manager (does not start servers yet)."""
    global _manager
    if _manager is None:
        _manager = MCPManager()
    return _manager


def get_manager() -> MCPManager:
    if _manager is None:
        return init_manager()
    return _manager