"""MCP server config loader."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MCPServerSpec:
    name: str
    command: str
    args: list[str]
    env: dict[str, str]
    description: str = ""

    @classmethod
    def from_dict(cls, name: str, d: dict) -> "MCPServerSpec":
        return cls(
            name=name,
            command=d.get("command", ""),
            args=list(d.get("args", [])),
            env=dict(d.get("env", {})),
            description=d.get("description", ""),
        )


def load_servers(file_path: str | None = None) -> dict[str, MCPServerSpec]:
    """Load MCP server specs from JSON file."""
    path = Path(file_path or settings.mcp_servers_file)
    if not path.exists():
        logger.warning("mcp_servers_file_missing", path=str(path))
        return {}

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error("mcp_servers_load_failed", path=str(path), error=str(e))
        return {}

    out: dict[str, MCPServerSpec] = {}
    for name, spec in raw.items():
        try:
            out[name] = MCPServerSpec.from_dict(name, spec)
        except Exception as e:
            logger.warning("mcp_server_parse_failed", name=name, error=str(e))
    return out