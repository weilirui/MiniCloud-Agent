# minicloud-agent

> Mini Agent 平台，具备 **RAG**、**Skills**、**MCP**、**上下文管理** 等能力，对标 Claude Code 的 demo 实现。

## ✨ 功能

| 模块 | 实现 |
|---|---|
| 🤖 **Agent Loop** | OpenAI 兼容协议（DeepSeek/Qwen/Moonshot/GPT 通用），tool_calls 自动执行 |
| 🧰 **Skills 系统** | 6 个内置 Skill（`/echo` `/init` `/code-review` `/rag` `/git` `/search`），本地注册表，支持自定义 |
| 🔌 **MCP 集成** | stdio 客户端，预置 filesystem + fetch，可热重启 |
| 📚 **RAG** | 文档上传 → 分块 → embedding → Qdrant，支持 PDF/MD/code/text；**混合检索**（向量 + BM25 融合 + MMR 去重） |
| 🧠 **上下文管理** | 滑动窗口 + token 计数 + 超额自动摘要压缩 |
| 💬 **流式 UI** | SSE 流式对话，工具调用可视化，三栏布局（会话 / 聊天 / Skills+知识库） |
| 🗄 **持久化** | PostgreSQL（会话/消息/工具调用/知识库元数据）+ Qdrant（向量） |
| 🛡 **稳定性** | 指数退避重试 + 超时 + 熔断器（CLOSED/OPEN/HALF_OPEN） |
| 🧪 **Prompt 工程** | 多版本管理 + 按 session 哈希的确定性 A/B 分流 |
| 📊 **可观测性** | token/成本按模型计价并落库（`llm_usage`） |
| 🔁 **反馈闭环** | 用户评分回流，`<4` 星自动标记坏例并导出 JSONL |
| ✅ **测试与评测** | 262 个用例（70% 覆盖率）+ 检索评测 + Agent 轨迹评测 + 生成质量评测 |

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
│   │   ├── core/                # llm, agent, context, memory, prompts,
│   │   │                        # retry, prompt_store
│   │   ├── rag/                 # embeddings, qdrant_store, chunker, ingest,
│   │   │                        # retriever, lexical (BM25), hybrid (融合+MMR)
│   │   ├── skills/              # base, registry, loader, invoker, builtin/*
│   │   ├── mcp/                 # client, manager, adapter, config
│   │   ├── db/                  # base, session, models
│   │   ├── api/                 # chat, sessions, rag, skills, mcp, health,
│   │   │                        # feedback
│   │   ├── observability/       # cost (token/成本计量与落库)
│   │   ├── feedback/            # service (评分收集与坏例导出)
│   │   ├── schemas/             # Pydantic schemas
│   │   └── utils/               # streaming, token_counter, logging, errors
│   ├── tests/                   # unit / integration / e2e + fakes
│   ├── eval/                    # datasets / metrics / stores / runner
│   ├── scripts/                 # build_golden_dataset.py
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
├── docs/                        # 用户文档 + 测试报告 + 评测指南
├── .github/workflows/ci.yml
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
| `POST` | `/api/v1/feedback/` | 提交评分（返回 `label=bad/good`） |
| `GET` | `/api/v1/feedback/stats` | 反馈统计（总量 / 差评数 / 差评率） |
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
make up                # 启动所有服务
make down              # 停止
make logs              # 查看日志
make build             # 重新构建
make ps                # 状态

make test              # 单元 + 联调 + e2e（无需外部服务），约 5 秒
make test-cov          # 同上并输出覆盖率
make test-integration  # 额外连接真实 PostgreSQL / Qdrant
make backend-test      # 在容器内跑

make golden            # 重新生成评测黄金集
make eval              # 离线检索评测（哈希向量，只能相对比较）
make eval-semantic     # 本地语义模型 bge-small-zh（免费，可作绝对数值）
make eval-qdrant       # 真实 Qdrant（默认仍是哈希向量）
make eval-real         # 托管 embedding API（产生费用）
make eval-agent        # Agent 工具选择评测（真实 LLM，产生费用）
make eval-online       # Agent 轨迹 + 生成质量（真实 LLM，产生费用）
```

若依赖装在虚拟环境里，加 `PY=<venv>/Scripts/python`（Windows）或 `PY=<venv>/bin/python`。

## 🧪 测试与评测

```bash
cd backend
pytest -q                    # 245 passed / 17 skipped（无外部服务）
pytest -q --run-integration  # 262 passed（含真实 PG / Qdrant）
```

- 分层：`unit` / `integration`（Agent Loop + PG + Qdrant）/ `e2e`
- Agent Loop 用可编排的 `FakeLLM` 测试，不花钱、不联网
- 覆盖率 **70%**，`core/agent.py` 93%、`rag/hybrid.py` 100%、`core/retry.py` 99%

检索评测（12 篇语料 / 29 块 / 50 条查询，top_k=5），语义向量 bge-small-zh-v1.5：

| 策略 | recall@5 | MRR | nDCG@5 |
|---|---|---|---|
| 纯向量（基线） | 0.9300 | 0.8473 | 0.8635 |
| 混合检索 | **0.9700** | **0.9083** | **0.9200** |
| 混合 + MMR | **0.9700** | **0.9083** | **0.9200** |

Recall@5 +4.3%，MRR +7.2%。同一份黄金集用哈希向量跑是 0.81 → 0.97（+19.8%），
但那组放大了优化幅度——哈希向量没有语义，把基线压低了。**对外请用上面这组。**

Agent 评测（20 条任务，deepseek-flash）：工具选择准确率 0.6792、完全匹配 0.45，
并暴露出模型倾向于冗余调用工具（单任务最多触发 6 次调用打满迭代上限）。
生成质量（50 条）：`lexical_support` 0.8011、`citation_rate` 0.9800。

详见 [`docs/testing-report.md`](docs/testing-report.md) 与 [`docs/eval-guide.md`](docs/eval-guide.md)。

详见 [`SPEC.md`](SPEC.md) 和 [`ARCHITECTURE.md`](ARCHITECTURE.md)。