# Getting Started

## 前置条件

- Docker 24+ / Docker Compose v2+
- 一份 OpenAI 兼容的 API key（OpenAI / DeepSeek / Qwen / Moonshot 都可）

## 一键启动

```bash
# 1. 复制环境变量模板
cp .env.example .env

# 2. 编辑 .env，填入 OPENAI_API_KEY（必填）和 OPENAI_BASE_URL（如果不是 OpenAI 官方）
vim .env

# 3. 启动
docker compose up -d

# 4. 等服务起来（约 30s），打开浏览器
# 前端：http://localhost:5173
# 后端 API 文档：http://localhost:8000/docs
```

## 验证

```bash
# 健康检查
curl http://localhost:8000/api/v1/health

# 列出可用 Skills
curl http://localhost:8000/api/v1/skills/

# 列 MCP servers
curl http://localhost:8000/api/v1/mcp/servers
```

## 本地开发（脱离 Docker）

后端：
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

前端：
```bash
cd frontend
npm install
npm run dev
```

## 故障排查

| 症状 | 排查 |
|---|---|
| 后端连不上 PG | 检查 `POSTGRES_HOST` 在容器内应等于 `postgres`，本地 dev 时改为 `localhost` |
| Qdrant 报 dimension mismatch | 确认 `EMBEDDING_DIM` 与 collection 一致 |
| MCP server 起不来 | 检查 `mcp.servers.json` 中的 `command`/`args` 是否在容器内可用（Node 22 / uv 已预装） |