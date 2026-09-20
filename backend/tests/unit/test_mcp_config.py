"""Unit tests for the MCP server config loader."""

from __future__ import annotations

import json

from app.mcp.config import MCPServerSpec, load_servers


def test_spec_from_dict_fills_defaults():
    spec = MCPServerSpec.from_dict("fs", {"command": "npx", "args": ["-y", "server"]})
    assert spec.name == "fs"
    assert spec.command == "npx"
    assert spec.args == ["-y", "server"]
    assert spec.env == {}
    assert spec.description == ""


def test_spec_from_dict_keeps_optional_fields():
    spec = MCPServerSpec.from_dict(
        "fs", {"command": "npx", "args": [], "env": {"A": "1"}, "description": "文件系统"}
    )
    assert spec.env == {"A": "1"}
    assert spec.description == "文件系统"


def test_load_servers_reads_file(tmp_path):
    path = tmp_path / "mcp.json"
    path.write_text(
        json.dumps(
            {
                "filesystem": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem"],
                    "env": {},
                    "description": "读文件",
                }
            }
        ),
        encoding="utf-8",
    )

    servers = load_servers(str(path))
    assert "filesystem" in servers
    assert servers["filesystem"].command == "npx"
    assert servers["filesystem"].description == "读文件"


def test_load_servers_missing_file_returns_empty(tmp_path):
    assert load_servers(str(tmp_path / "nope.json")) == {}


def test_load_servers_malformed_json_returns_empty(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    assert load_servers(str(path)) == {}


def test_project_servers_file_is_present(backend_dir):
    """The shipped config must stay loadable - a typo here breaks startup."""
    servers = load_servers(str(backend_dir / "mcp.servers.json"))
    assert isinstance(servers, dict)
    assert "filesystem" in servers
