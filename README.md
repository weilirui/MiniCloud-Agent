# minicloud-agent

> Mini Agent 平台，具备 **RAG**、**Skills**、**MCP**、**上下文管理** 等能力，对标 Claude Code 的 demo 实现。

## ✨ 功能

| 模块 | 实现 |
|---|---|
| 🤖 **Agent Loop** | OpenAI 兼容协议（DeepSeek/Qwen/Moonshot/GPT 通用），tool_calls 自动执行 |
| 🧰 **Skills 系统** | 6 个内置 Skill（`/echo` `/init` `/code-review` `/rag` `/git` `/search`），本地注册表，支持自定义 |
| 🔌 **MCP 集成** | stdio 客户端，预置 filesystem + fetch，可热重启 |
| 📚 **RAG** | 文档上传 → 分块 → embedding → Qdrant，支持 PDF/MD/code/text |
| 🧠 **上下文管理** | 滑动窗口 + token 计数 + 超额自动摘要压缩 |
| 💬 **流式 UI** | SSE 流式对话，工具调用可视化，三栏布局（会话 / 聊天 / Skills+知识库） |
| 🗄 **持久化** | PostgreSQL（会话/消息/工具调用/知识库元数据）+ Qdrant（向量） |

## 🚀 快速开始

```bash
# 1. 复制环境变量
cp .env.example .env
# 编辑 .env，至少填 OPENAI_API_KEY

# 2. 一键启动（Docker Compose）
docker compose up -d

# 3. 打开
# 前端:  http://localhost:5173
# API:   http://localhost:8000/docs
# Qdrant: http://localhost:6333/dashboard
```

## 📁 目录结构

```
minicloud-agent/
├── backend/                     # Python FastAPI
│   ├── app/
│   │   ├── main.py              # FastAPI factory + lifespan
│   │   ├── config.py            # pydantic-settings
│   │   ├── core/                # llm, agent, context, memory, prompts
│   │   ├── rag/                 # embeddings, qdrant, chunker, ingest, retriever
│   │   ├── skills/              # base, registry, loader, invoker, builtin/*
│   │   ├── mcp/                 # client, manager, adapter, config
│   │   ├── db/                  # base, session, models
│   │   ├── api/                 # chat, sessions, rag, skills, mcp, health
│   │   ├── schemas/             # Pydantic schemas
│   │   └── utils/               # streaming, token_counter, logging, errors
│   ├── alembic/                 # 迁移
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/                    # React + Vite + TypeScript
│   ├── src/
│   │   ├── api/                 # chat (SSE), sessions, skills, rag
│   │   ├── store/               # Zustand stores
│   │   ├── components/          # ChatWindow, MessageBubble, ToolCallCard, ...
│   │   └── pages/ChatPage.tsx
│   └── Dockerfile
├── docs/                        # 用户文档
├── docker-compose.yml
└── .env.example
```

## 🔌 API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/v1/chat/stream` | **SSE 流式对话** |
| `POST` | `/api/v1/chat/completions` | 非流式 |
| `GET` | `/api/v1/sessions/` | 列出所有会话 |
| `POST` | `/api/v1/sessions/` | 新建会话 |
| `GET` | `/api/v1/sessions/{id}` | 会话详情（含消息） |
| `POST` | `/api/v1/rag/upload` | 上传文件入库 |
| `POST` | `/api/v1/rag/query` | 检索知识库 |
| `GET` | `/api/v1/rag/docs` | 列出知识库 |
| `DELETE` | `/api/v1/rag/docs/{id}` | 删除文档 |
| `GET` | `/api/v1/skills/` | 列出所有 Skills |
| `POST` | `/api/v1/skills/invoke` | 直接调用 Skill |
| `GET` | `/api/v1/mcp/servers` | MCP server 状态 |
| `POST` | `/api/v1/mcp/servers/{name}/restart` | 重启 MCP server |
| `GET` | `/api/v1/health` | 健康检查 |

## 🧰 内置 Skills

| Trigger | 名称 | 说明 |
|---|---|---|
| `/echo <text>` | echo | 回显输入 |
| `/init` | project_init | 扫描项目生成说明书 |
| `/code-review <path>` | code_review | 审查代码 |
| `/rag <query>` | rag_qa | 从知识库检索回答 |
| `/git [detail]` | git_status | git 状态总结 |
| `/search <query>` | web_search | 联网搜索（需 TAVILY_API_KEY） |

自定义 Skill：放到 `backend/app/skills/builtin/<name>/` 或 `data/skills/<name>/`，重启即可。

## 🔌 MCP 集成

预置 2 个 server（`mcp.servers.json`）：
- **filesystem** —— `npx -y @modelcontextprotocol/server-filesystem`
- **fetch** —— `uvx mcp-server-fetch`

可在 `backend/mcp.servers.json` 添加更多。

## 🛠 开发命令

```bash
make up         # 启动所有服务
make down       # 停止
make logs       # 查看日志
make build      # 重新构建
make ps         # 状态
make backend-test  # 跑测试
```

详见 [`SPEC.md`](SPEC.md) 和 [`ARCHITECTURE.md`](ARCHITECTURE.md)。