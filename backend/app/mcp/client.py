"""MCP stdio client wrapper.

Provides a thin async interface around the official `mcp` SDK:
- start a server (subprocess)
- list tools
- call a tool
"""

from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Any

# Import lazily to avoid hard dep at import time
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    MCP_AVAILABLE = True
except ImportError:  # pragma: no cover
    MCP_AVAILABLE = False
    ClientSession = None  # type: ignore
    StdioServerParameters = None  # type: ignore
    stdio_client = None  # type: ignore

from app.mcp.config import MCPServerSpec
from app.utils.errors import MCPServerError
from app.utils.logging import get_logger

logger = get_logger(__name__)


class MCPClient:
    """A single connected MCP server.

    Lifecycle: connect() -> ... -> close()
    """

    def __init__(self, spec: MCPServerSpec) -> None:
        self.spec = spec
        self._session: ClientSession | None = None
        self._exit_stack: AsyncExitStack | None = None
        self._tools: list[dict] = []
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        if not MCP_AVAILABLE:
            raise MCPServerError(
                "mcp SDK not available. Install with: pip install mcp",
                code="mcp_unavailable",
            )
        if self._connected:
            return

        self._exit_stack = AsyncExitStack()
        try:
            params = StdioServerParameters(
                command=self.spec.command,
                args=self.spec.args,
                env={**self.spec.env} if self.spec.env else None,
            )
            read, write = await self._exit_stack.enter_async_context(
                stdio_client(params)
            )
            self._session = await self._exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            await self._session.initialize()
            await self._refresh_tools()
            self._connected = True
            logger.info("mcp_connected", server=self.spec.name, tools=len(self._tools))
        except Exception as e:
            logger.error("mcp_connect_failed", server=self.spec.name, error=str(e))
            await self.close()
            raise MCPServerError(
                f"MCP server '{self.spec.name}' connect failed: {e}",
                code="mcp_connect_failed",
            )

    async def _refresh_tools(self) -> None:
        if not self._session:
            return
        try:
            result = await self._session.list_tools()
            self._tools = [
                {
                    "name": t.name,
                    "description": t.description or "",
                    "parameters": t.inputSchema or {"type": "object", "properties": {}},
                    "server": self.spec.name,
                }
                for t in result.tools
            ]
        except Exception as e:
            logger.warning("mcp_list_tools_failed", server=self.spec.name, error=str(e))
            self._tools = []

    async def list_tools(self) -> list[dict]:
        return list(self._tools)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        if not self._session or not self._connected:
            raise MCPServerError(f"MCP server '{self.spec.name}' not connected")
        try:
            result = await self._session.call_tool(name, arguments)
            # result.content is a list of content blocks
            parts = []
            for block in (result.content or []):
                if hasattr(block, "text"):
                    parts.append(block.text)
                else:
                    parts.append(str(block))
            return "\n".join(parts) or ""
        except Exception as e:
            logger.error("mcp_call_tool_failed",
                         server=self.spec.name, tool=name, error=str(e))
            raise MCPServerError(f"MCP tool call failed: {e}") from e

    async def close(self) -> None:
        if self._exit_stack:
            try:
                await self._exit_stack.aclose()
            except Exception:
                pass
            self._exit_stack = None
        self._session = None
        self._connected = False