# SPEC.md —— minicloud-agent 模块清单

> 这是整个项目的"设计蓝图"。每个文件都列出了**职责**与**关键依赖**。
> 在动手写代码前，请逐项确认。修改 SPEC 后再写代码。

---

## 0. 全局约束

- **Python ≥ 3.11**，**Node ≥ 20**。
- 后端包名统一使用 `minicloud.*` 命名空间，模块导入路径 `app.xxx`（实际包名在 pyproject.toml 中）。
- 所有外部 IO（LLM / Qdrant / PG）必须支持 **异步**。
- 配置统一从 `.env` 读取，**禁止在代码里硬编码 API key**。
- LLM 调用必须支持流式（SSE）和非流式两种模式。
- 所有工具调用必须记录到 `tool_invocations` 表（可观测 + 回放）。
- 每一轮工具调用必须完整落库到 `messages`：请求工具的 `assistant`（含 `tool_calls`）与每条 `tool` 结果各自成行。
  存储保留 provider 格式以便直接回喂 LLM，UI 侧再由 API 转成扁平形状；
  **不允许**只在内存上下文里执行工具而不落库——否则重开会话会丢失整条工具轨迹。
- 日志统一用 `structlog`，关键事件（tool call / llm call / mcp spawn）必须记录。

---

## 1. 仓库结构

```
minicloud-agent/
├── README.md                       # 项目入口
├── SPEC.md                         # 本文件
├── ARCHITECTURE.md                 # 架构详解
├── docker-compose.yml              # PG + Qdrant + Backend + Frontend
├── .env.example                    # 环境变量模板
├── .gitignore
├── Makefile                        # dev/test/up/down/logs/eval 便捷命令
├── .github/workflows/ci.yml        # lint → 建黄金集 → 测试 → 离线评测
│
├── backend/                        # Python 后端
│   ├── app/                        # 应用代码
│   ├── tests/                      # unit / integration / e2e
│   ├── eval/                       # 检索评测（数据集 / 指标 / 运行器）
│   ├── scripts/                    # 数据集构建脚本
│   └── alembic/                    # 数据库迁移
├── frontend/                       # React 前端
├── data/                           # 运行时持久化（git ignore）
└── docs/                           # 用户文档 / 测试报告 / 评测指南
```

---

## 2. backend/ —— 详细模块清单

### 2.1 入口与配置

| 文件 | 职责 |
|---|---|
| `backend/pyproject.toml` | 依赖管理（uv/pip 兼容），锁定版本区间 |
| `backend/Dockerfile` | 多阶段构建，启动 uvicorn |
| `backend/alembic.ini` | 数据库迁移配置 |
| `backend/app/main.py` | FastAPI app 工厂，挂载路由、CORS、middleware、lifespan |
| `backend/app/config.py` | `Settings` 类（pydantic-settings），从 .env 读全部配置 |
| `backend/app/deps.py` | FastAPI Depends 工厂（DB session / Qdrant client / LLM client） |

### 2.2 app/core/ —— Agent 核心

| 文件 | 职责 | 关键依赖 |
|---|---|---|
| `core/llm.py` | OpenAI 兼容 LLM 客户端封装，统一流式/非流式接口 | `openai`, `httpx` |
| `core/agent.py` | **Agent Loop**：解析 tool_calls → 执行工具 → 把结果回喂 LLM → 循环直到 finish | LangChain `BaseChatModel` |
| `core/context.py` | 上下文管理：消息裁剪 / 摘要压缩 / token 预算（按模型窗口动态调整） | `tiktoken` 或 model 自带 tokenizer |
| `core/memory.py` | 记忆抽象：`WorkingMemory`（本会话滑动窗口）+ `LongTermMemory`（PG + Qdrant） | - |
| `core/prompts.py` | 系统提示词模板（带 Skills 列表 / MCP 工具列表注入） | - |
| `core/retry.py` | **稳定性**：指数退避 + 抖动的重试策略、`with_timeout` 超时包装、`CircuitBreaker` 熔断器（CLOSED / OPEN / HALF_OPEN） | - |
| `core/prompt_store.py` | **Prompt 工程**：多版本注册、默认版本切换、Jinja 渲染、按 `session_id` MD5 分桶的确定性 A/B 分流、JSON 落盘 | - |

### 2.3 app/rag/ —— 检索增强生成

| 文件 | 职责 | 关键依赖 |
|---|---|---|
| `rag/embeddings.py` | Embedding 客户端（OpenAI 兼容协议，支持 batch） | `openai` |
| `rag/qdrant_store.py` | Qdrant 客户端封装：collection 管理、CRUD、metadata filter | `qdrant-client` |
| `rag/chunker.py` | 文档分块：按 token 数 + 重叠，支持 markdown / code / plain | `langchain-text-splitters` |
| `rag/ingest.py` | 入库流水线：读文件 → 分块 → embedding → 写入 Qdrant | - |
| `rag/retriever.py` | **检索入口**：`rag_hybrid_enabled` 打开时走 `HybridRetriever`，混合链路任何异常退回纯向量；`invalidate_lexical_index()` 供入库/删除调用 | - |
| `rag/corpus_index.py` | `CorpusLexicalIndex`：从 Qdrant 滚动重建 BM25 索引，惰性 + dirty 标记（批量入库只滚一次），chunk id 用 `hit_id()` 派生以保证与稠密分支一致；重建失败静默降级 | - |
| `rag/lexical.py` | **词法检索**：`tokenize()`（拉丁词串 + CJK 一元/二元切分，无需分词器）、BM25 打分、`LexicalIndex` | - |
| `rag/hybrid.py` | **混合检索**：向量 + BM25 双路召回 → min-max 归一化加权融合或 RRF → MMR 多样性重排（词元 Jaccard，零额外 embedding 调用）；`hit_id()` 兼容不同适配器的 id 字段名 | - |

### 2.4 app/skills/ —— Skills 系统

| 文件 | 职责 | 关键依赖 |
|---|---|---|
| `skills/base.py` | `Skill` 基类 / `SkillContext`（提供 LLM / RAG / MCP 访问） | pydantic |
| `skills/registry.py` | 本地 Skills 注册表：扫描内置目录 + 用户自定义目录 | - |
| `skills/loader.py` | 加载 `SKILL.md` 描述文件（Markdown frontmatter 解析） | `python-frontmatter` |
| `skills/invoker.py` | 调度器：根据用户输入 / slash command 匹配 Skill 并执行 | - |
| `skills/builtin/...` | 内置 Skills 目录，每个 Skill 一个子目录 | - |

#### 内置 Skills 列表（首版）

| Skill 名 | 触发词 | 功能 |
|---|---|---|
| `code_review` | `/code-review` | 对指定文件做代码审查，输出 diff 建议 |
| `project_init` | `/init` | 扫描项目结构，生成 `MINICLOUD.md` 项目说明书（类比 CLAUDE.md） |
| `rag_qa` | `/rag <query>` | 从知识库检索并回答 |
| `git_status` | `/git` | 查看 git 状态 + 总结 |
| `web_search` | `/search <q>` | 联网搜索（对接 Tavily/Serper API） |

### 2.5 app/mcp/ —— Model Context Protocol

| 文件 | 职责 | 关键依赖 |
|---|---|---|
| `mcp/client.py` | MCP stdio 客户端（spawn 子进程，JSON-RPC over stdio） | `mcp` 官方 Python SDK |
| `mcp/manager.py` | MCP server 生命周期管理：启动 / 健康检查 / 重启 / 关闭 | - |
| `mcp/adapter.py` | 把 MCP `tools/list` 转换为 Agent 可消费的 `Tool` 对象 | - |
| `mcp/config.py` | MCP server 配置加载（从 `mcp.servers.json`） | - |
| `mcp/servers.example.json` | MCP server 配置示例 | - |

#### 首版预置 MCP server

- `filesystem` —— 官方 `@modelcontextprotocol/server-filesystem`
- `fetch` —— 官方 fetch server（HTTP GET）
- `git` —— 官方 git server（可选）

### 2.6 app/db/ —— 数据库模型与访问

| 文件 | 职责 |
|---|---|
| `db/base.py` | SQLAlchemy `DeclarativeBase` |
| `db/session.py` | async engine + `async_sessionmaker` |
| `db/models.py` | 表模型：`Session`, `Message`, `ToolInvocation`, `KnowledgeDoc`, `UserPreference`, `LLMUsage`, `MessageFeedback` |
| `db/migrations/` | Alembic 自动生成 |

#### 数据模型一览

| 表 | 关键字段 |
|---|---|
| `sessions` | id, title, created_at, updated_at, model, system_prompt |
| `messages` | id, session_id, role, content, tool_calls(jsonb), tool_call_id, created_at |
| `tool_invocations` | id, message_id, skill_or_tool, args(jsonb), result, duration_ms, status |
| `knowledge_docs` | id, filename, source_type, qdrant_point_ids, uploaded_at |
| `user_preferences` | key, value(jsonb), updated_at（KV 表，存默认模型、温度等） |
| `llm_usage`（新增） | id, session_id, model, endpoint, prompt_tokens, completion_tokens, total_tokens, latency_ms, cost_usd, created_at |
| `message_feedback`（新增） | id, session_id, message_id, rating(1-5), query, answer, comment, tags(jsonb), created_at |

> 后两张表由迁移 `alembic/versions/0002_usage_feedback.py` 建立。

### 2.7 app/api/ —— HTTP 路由

| 路由前缀 | 文件 | 功能 |
|---|---|---|
| `/api/v1/health` | `health.py` | 健康检查（PG/Qdrant 连通性） |
| `/api/v1/chat` | `chat.py` | `POST /stream`（SSE 流式对话）、`POST /completions` |
| `/api/v1/sessions` | `sessions.py` | 会话 CRUD：列表、创建、删除、获取历史 |
| `/api/v1/rag` | `rag.py` | `POST /upload`（上传文件）、`POST /query`（检索）、`DELETE /docs/{id}` |
| `/api/v1/skills` | `skills.py` | `GET /`（列表）、`GET /{name}`（详情）、`POST /invoke` |
| `/api/v1/mcp` | `mcp.py` | `GET /servers`、`POST /servers/{name}/restart` |
| `/api/v1/feedback`（新增） | `feedback.py` | `POST /`（提交评分，返回 `label=bad/good`）、`GET /stats`（总量/差评数/差评率） |

### 2.8 app/schemas/ —— Pydantic 模型

| 文件 | 内容 |
|---|---|
| `chat.py` | `ChatRequest`, `ChatChunk`（SSE 事件类型） |
| `session.py` | `SessionCreate`, `SessionOut`, `MessageOut` |
| `rag.py` | `UploadResponse`, `QueryRequest`, `QueryResponse` |
| `skill.py` | `SkillInfo`, `SkillInvokeRequest` |
| `mcp.py` | `MCPServerConfig`, `MCPServerStatus` |
| `feedback.py`（新增） | `FeedbackCreate`, `FeedbackOut`, `FeedbackStats` |

### 2.9 app/utils/

| 文件 | 职责 |
|---|---|
| `utils/streaming.py` | SSE 响应生成器（`text/event-stream` 格式） |
| `utils/token_counter.py` | Token 计数（按模型适配） |
| `utils/logging.py` | structlog 配置 |
| `utils/errors.py` | 自定义异常 + FastAPI 异常处理器 |

### 2.10 app/observability/ —— 成本与用量

| 文件 | 职责 |
|---|---|
| `observability/cost.py` | 按模型的每百万 token 计价表、`estimate_cost()`、`UsageRecord`、`CostTracker`（按 model/endpoint 聚合）、`db_usage_sink()` 落 `llm_usage` 表 |

### 2.11 app/feedback/ —— 反馈闭环

| 文件 | 职责 |
|---|---|
| `feedback/service.py` | `FeedbackRecord`、`FeedbackService.submit/negative/stats/export_jsonl`；`rating < 4` 判定为坏例，可导出 JSONL 用于人工标注或 SFT |

### 2.12 backend/tests/ —— 测试

> 现状：**262 个用例全部通过，覆盖率 70%**。服务不可达时集成用例自动 skip，保证默认套件永远可跑。

| 路径 | 覆盖范围 |
|---|---|
| `tests/conftest.py` | 环境变量预置（`app.config` 在 import 时实例化，必须先注入 `OPENAI_API_KEY`）、`--run-integration` / `--run-live` 开关、公共 fixture |
| `tests/fakes/fake_llm.py` | `FakeLLM`：按脚本产出 `content` / `tool_calls` / `error`，同时实现 `chat()` 与 `stream()` 并记录每次调用，让 Agent Loop 不花钱也能测 |
| `tests/unit/` | 16 个文件：token 计数、分块、上下文、Skills、重试/熔断、混合检索、Prompt 版本、成本、反馈、记忆、SSE、入库、MCP 配置、异常、Schema |
| `tests/integration/test_agent_loop.py` | Agent 循环 14 例（**不需要外部服务**）：工具路由、未知工具、迭代上限、并行工具调用、摘要触发、错误传播 |
| `tests/integration/test_db_persistence.py` | 真实 PostgreSQL：会话/消息往返、级联删除、工具审计、`llm_usage`、`message_feedback`、sessions 与 feedback 的 HTTP 层 |
| `tests/integration/test_qdrant_rag.py` | 真实 Qdrant：写入/检索/删除/计数、混合检索跑在真实向量库上 |
| `tests/e2e/test_smoke.py` | HTTP 冒烟（裸 FastAPI 实例，只挂 health + skills，避免 lifespan 拉起 MCP 子进程） |

### 2.13 backend/eval/ —— 评测

| 路径 | 职责 |
|---|---|
| `eval/datasets/` | `corpus.jsonl`（12 篇项目语料）、`queries.jsonl`（50 条查询）、`golden_retrieval.jsonl`（脚本生成的相关块 id）、`agent_tasks.jsonl`（20 条 Agent 任务） |
| `eval/metrics/retrieval.py` | `recall@k` `precision@k` `hit_rate@k` `MRR` `nDCG@k` |
| `eval/metrics/generation.py` | `lexical_support`（离线）、`citation_rate`、`llm_faithfulness`（LLM-as-judge） |
| `eval/metrics/agent.py` | `tool_selection_acc`、`tool_selection_exact`、`task_success_rate`（只统计声明了 `must_contain` 的任务）、`avg_steps` |
| `eval/stores/` | `memory.py`（内存向量库）、`qdrant.py`（包装生产 `QdrantStore`） |
| `eval/offline_embedder.py` | `HashingEmbedder`：词袋固定种子随机投影，离线可复现，**只用于策略间相对比较** |
| `eval/local_embedder.py` | `LocalEmbedder`：本地 `bge-small-zh-v1.5`（ONNX/CPU，512 维），免 key 免费用，产出可作绝对数值的语义向量 |
| `eval/runner.py` | 检索评测：对比 `vector` / `hybrid` / `hybrid_mmr`，`--embedder offline\|local\|openai`，输出 `eval/reports/eval_report.{md,json}` |
| `eval/online_runner.py` | 在线评测：`--suite agent`（20 条任务跑真实 Agent 循环）与 `--suite generation`（50 条查询测 groundedness），输出 `online_eval_report.{md,json}` |
| `scripts/build_golden_dataset.py` | 由语料 + 查询推导黄金集（不手写标注） |

> `eval/online_runner.py` 中的 MCP 工具只声明、由 stub 执行（真实 MCP server 需要 npx + 联网安装），
> 因此工具选择准确率有意义，MCP 任务上的 `task_success_rate` 只反映 stub 回显。

---

## 3. frontend/ —— 详细模块清单

### 3.1 项目配置

| 文件 | 职责 |
|---|---|
| `frontend/package.json` | 依赖：react / vite / tailwind / zustand / react-markdown / highlight.js |
| `frontend/vite.config.ts` | Vite 配置：dev server 5173、proxy `/api` → backend:8000 |
| `frontend/tailwind.config.js` | 暗色主题配色 |
| `frontend/Dockerfile` | 多阶段构建（Node build → nginx serve） |
| `frontend/index.html` | HTML 入口 |
| `frontend/nginx.conf` | SPA fallback + API 反代 |

### 3.2 src/

| 文件 | 职责 |
|---|---|
| `main.tsx` | ReactDOM 渲染入口 |
| `App.tsx` | 顶层布局：左会话列表 / 右聊天区 |
| `api/chat.ts` | SSE 流式客户端（fetch + ReadableStream） |
| `api/sessions.ts` | 会话 CRUD 客户端 |
| `api/skills.ts` | Skills 列表/调用客户端 |
| `api/rag.ts` | 知识库上传/查询客户端 |
| `store/session.ts` | Zustand store：当前会话、消息列表、流式状态 |
| `store/skills.ts` | Zustand store：可用 Skills |
| `components/ChatWindow.tsx` | 聊天主面板，自动滚动 |
| `components/MessageBubble.tsx` | 单条消息气泡（user / assistant / tool） |
| `components/ToolCallCard.tsx` | 工具调用可视化卡片（skill 名 + 参数 + 结果） |
| `components/SessionList.tsx` | 左侧会话列表 |
| `components/SkillPanel.tsx` | 右侧可用 Skills 面板 |
| `components/RagUpload.tsx` | 知识库文件上传组件 |
| `components/SlashCommandHint.tsx` | 输入 `/` 时弹出可用 Skills 列表 |
| `pages/ChatPage.tsx` | 默认页（聊天 + 工具 + Skills） |

---

## 4. docker-compose.yml 服务清单

| 服务 | 镜像 | 端口 | 数据卷 | 依赖 |
|---|---|---|---|---|
| `postgres` | `postgres:16-alpine` | 5432 | `data/postgres` | - |
| `qdrant` | `qdrant/qdrant:v1.12.0` | 6333/6334 | `data/qdrant` | - |
| `backend` | 本地构建（`backend/Dockerfile`） | 8000 | `data/uploads` | postgres, qdrant |
| `frontend` | 本地构建（`frontend/Dockerfile`） | 5173/80 | - | backend |

---

## 5. .env.example 关键变量

```env
# LLM
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini

# Embedding（可与 LLM 不同的 endpoint）
EMBEDDING_API_KEY=sk-xxx
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small

# 数据库
POSTGRES_USER=minicloud
POSTGRES_PASSWORD=minicloud
POSTGRES_DB=minicloud
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# Qdrant
QDRANT_URL=http://qdrant:6333
QDRANT_API_KEY=

# Skills
SKILLS_DIR=/app/skills

# MCP
MCP_SERVERS_FILE=/app/mcp.servers.json

# 应用
APP_PORT=8000
LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:5173
```

---

## 6. 依赖清单（pyproject.toml 摘要）

```toml
# Web framework
fastapi = "^0.115"
uvicorn[standard] = "^0.32"

# LLM
openai = "^1.50"
tiktoken = "^0.8"

# Agent / LangChain
langchain = "^0.3"
langchain-core = "^0.3"
langchain-openai = "^0.2"

# RAG
qdrant-client = "^1.12"
langchain-text-splitters = "^0.3"

# MCP
mcp = "^1.0"   # 官方 Python SDK

# DB
sqlalchemy[asyncio] = "^2.0"
asyncpg = "^0.30"
alembic = "^1.13"

# Pydantic / Config
pydantic = "^2.9"
pydantic-settings = "^2.5"

# Utils
structlog = "^24.4"
httpx = "^0.27"
python-frontmatter = "^1.1"
python-multipart = "^0.0.12"

# Dev
pytest = "^8.3"
pytest-asyncio = "^0.24"
pytest-cov = "^6.0"
ruff = "^0.7"
```

---

## 7. 首版功能验收清单（demo 范围）

完成以下即可视为 demo 达成：

- [x] `docker compose up -d` 一键启动全部服务
- [ ] 前端能创建新会话、发消息，**SSE 流式**返回 assistant 回复
- [ ] LLM 在需要时调用 1+ 个内置 Skill，工具调用过程在前端可视化
- [ ] 上传 1 个 PDF/Markdown 到知识库，能用 `/rag` 或自然语言检索到
- [ ] 至少 1 个 MCP server（filesystem）成功连入，工具列表自动出现在 Agent 中
- [ ] 长会话超过 token 预算时自动压缩摘要
- [ ] `/api/v1/skills` 返回所有内置 Skills 描述
- [ ] Alembic 迁移在容器启动时自动执行

## 8. 工程化验收清单（已达成）

- [x] 分层测试：`unit` / `integration` / `e2e`，262 用例全绿
- [x] Agent Loop 用 `FakeLLM` 可离线回归，覆盖率 93%
- [x] 集成用例在真实 PostgreSQL / Qdrant 上验证通过（17 例由 skip 转 pass）
- [x] 覆盖率 70%，新增模块普遍 ≥ 94%
- [x] 检索评测：黄金集 + 指标 + 三策略对比，Recall@5 0.81 → 0.97
- [x] CI：`.github/workflows/ci.yml`（ruff → 建黄金集 → pytest 覆盖率卡口 → 离线评测）
- [x] 混合检索（BM25 + 向量 + MMR）、重试/熔断、Prompt 版本与 A/B、成本落库、反馈回流

> 未勾选的第 7 节条目属于"需要真实 LLM Key 才能人工验证"的部分，不阻塞工程化。