# MCP 配置说明

## 配置位置

`backend/mcp.servers.json`：

```json
{
  "<server_name>": {
    "command": "执行命令",
    "args": ["参数1", "参数2"],
    "env": {"KEY": "VALUE"},
    "description": "可选描述"
  }
}
```

## 已预置的 server

- **filesystem** —— `npx -y @modelcontextprotocol/server-filesystem /data/workspace`
- **fetch** —— `uvx mcp-server-fetch`

## 添加新的 MCP server

1. 找到该 server 的官方包名（一般是 npm 或 pypi）。
2. 在 `mcp.servers.json` 加一项。
3. 重启后端容器。

## 容器镜像预装

后端镜像内置：
- Node 22（用于 npx 运行 npm 包）
- uv（用于 uvx 运行 python 包）

如需其他运行时，编辑 `backend/Dockerfile` 添加安装步骤。