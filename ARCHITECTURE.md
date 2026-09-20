# ARCHITECTURE.md —— 架构详解

## 1. 数据流总览

```
┌────────────┐  SSE   ┌─────────────────────────────────────────────┐
│  React UI  │ <────> │ FastAPI                                    │
│ (Vite 5173)│        │  ├─ /api/v1/chat/stream (SSE)              │
└────────────┘        │  │     └─ Agent Loop                        │
                      │  │         ├─ LLM (OpenAI 兼容)              │
                      │  │         ├─ Skill Invoker                 │
                      │  │         │     └─ Built-in Skills         │
                      │  │         └─ MCP Adapter                  │
                      │  │               └─ MCP stdio client       │
                      │  │                     └─ filesystem mcp   │
                      │  ├─ /api/v1/rag/{upload,query}             │
                      │  ├─ /api/v1/skills/{list,invoke}           │
                      │  ├─ /api/v1/mcp/servers                    │
                      │  └─ /api/v1/feedback/{submit,stats}        │
                      │                                             │
                      │  横切：RetryPolicy / CircuitBreaker         │
                      │        CostTracker ──► llm_usage           │
                      │        FeedbackService ──► message_feedback│
                      │                                             │
                      │  ┌─────────────┐    ┌─────────────────────┐ │
                      │  │ PostgreSQL  │    │ Qdrant              │ │
                      │  │ (会话/消息) │    │ (embedding/记忆)    │ │
                      │  └─────────────┘    └─────────────────────┘ │
                      └─────────────────────────────────────────────┘
```

> 外部 IO 一律经过 `core/retry.py`：LLM 调用带指数退避重试与超时，
> 下游服务带熔断器（连续失败后 OPEN，冷却期结束进 HALF_OPEN 试探）。

## 2. Agent Loop 状态机

```
用户消息
   │
   ▼
[build_context] ──► 载入系统提示 + Skills 摘要 + MCP 工具摘要 + 历史
   │
   ▼
[llm_call] ──► 流式产出 content / tool_calls
   │
   ├─ finish_reason=stop         ──► 返回 SSE 结束事件
   │
   └─ finish_reason=tool_calls   ──► [execute_tools]
                                          │
                                          ▼
                                  ┌───────────────────────┐
                                  │ 解析 tool_calls, 路由:│
                                  │   ├─ skill_xxx    → Skill Invoker
                                  │   └─ mcp__xxx     → MCP Adapter
                                  └───────────────────────┘
                                          │
                                          ▼
                                  把 tool_results 追加到 messages
                                          │
                                          └──────► [llm_call] (循环)
```

**循环退出条件**：LLM 返回 `finish_reason=stop` 或达到 `max_iterations`（默认 10）。

## 3. Skills 系统设计

### 3.1 Skill 定义格式（SKILL.md）

```markdown
---
name: code_review
description: 对指定文件做代码审查，输出 diff 建议
trigger: "/code-review"
parameters:
  - name: path
    type: string
    required: true
---

# Code Review Skill

详细描述、用法、注意事项...
LLM 在调用此 Skill 前会读取此文件。
```

### 3.2 注册机制

- **内置 Skills**：随代码发布，在 `app/skills/builtin/<name>/` 下。
- **自定义 Skills**：用户放到 `data/skills/<name>/`（运行时挂载）。
- 注册表扫描时机：后端启动时（lifespan）。

### 3.3 LLM 如何感知 Skills

- 每次 LLM 调用前，`prompts.py` 注入一段：
  > "可用 Skills（用 `/<name>` 调用）：..."
- 工具调用时 LLM 输出 `tool_calls`，`tool.function.name = "skill_code_review"`。

## 4. MCP 集成

- 启动时读 `mcp.servers.json`，对每个 server `spawn` 子进程。
- 用官方 `mcp` Python SDK 走 stdio JSON-RPC。
- 调 `tools/list` 把工具列表转换为 Agent Tool 对象。
- 工具调用走 `tools/call`，把结果回喂。

**配置示例**：

```json
{
  "filesystem": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/data/workspace"],
    "env": {}
  }
}
```

## 5. 上下文管理

```
max_input_tokens (按模型动态)
   │
   ├─ system_prompt (~500 tokens)
   ├─ tools_schema (~1-3k tokens)
   ├─ skills_summary (~500 tokens)
   ├─ recent_messages (滑动窗口，默认 20 条)
   ├─ long_term_memory_retrieval (按当前 query 检索 top-k)
   │
   └─ if total > budget:
        ├─ 对中间消息做摘要压缩（保留最近 N 条）
        └─ 把摘要作为 system message 注入
```

## 6. RAG 流水线

### 入库

```
文件 (upload)
   │
   ▼
检测扩展名 → 选 loader (md/txt/pdf/code)
   │
   ▼
chunker (RecursiveCharacterTextSplitter, chunk=800, overlap=100)
   │
   ▼
embedding (OpenAI 兼容)
   │
   ▼
Qdrant upsert (point = {vector, payload={text, source, chunk_id}})
```

### 检索（混合检索）

```
query
   │
   ├──────────────────────────► embedding(query) ──► Qdrant search (top_k × 4)
   │                                                       │
   └──────────────────────────► BM25 词法检索 (top_k × 4) ──┤
                                                            ▼
                                              ┌──────────────────────────┐
                                              │ 1. min-max 归一化加权融合 │
                                              │    (或 RRF 倒数排名融合)  │
                                              │ 2. MMR 多样性重排         │
                                              │    (词元 Jaccard, 零成本) │
                                              └──────────────────────────┘
                                                            │
                                                            ▼
                                        返回 [{id, text, source, score,
                                               vector_score, lexical_score}]
```

命中 id 由 `hybrid.hit_id()` 统一解析（适配器字段名不一致：`id` / `chunk_id` /
`doc_id#chunk_index` / 文本摘要），因此换向量库实现不需要改融合层。

**实测收益**（12 篇语料 / 29 块 / 50 条查询，top_k=5）：

| 策略 | recall@5 | MRR | nDCG@5 |
|---|---|---|---|
| 纯向量 | 0.8100 | 0.6673 | 0.6973 |
| 混合检索 | 0.9500 | 0.8047 | 0.8405 |
| 混合 + MMR | **0.9700** | **0.8053** | **0.8415** |

## 6.5 Prompt 版本与 A/B

```
PromptStore
  ├─ register(name, version, template)   多版本共存
  ├─ set_default(name, version)          切默认，无需改代码
  ├─ assign(name, session_id)            按 session_id 的 MD5 分桶 → 确定性分流
  └─ render_for_session(name, session_id, **vars)
```

用哈希分桶而不是随机数，保证**同一会话始终命中同一版本**，否则用户会在两次提问之间
看到风格跳变。

## 7. 前端 SSE 流式消费

```ts
const resp = await fetch('/api/v1/chat/stream', {
  method: 'POST',
  body: JSON.stringify({session_id, message}),
});
const reader = resp.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const {done, value} = await reader.read();
  if (done) break;
  const chunk = decoder.decode(value);
  // 解析 SSE: "data: {json}\n\n"
}
```

## 8. 可观测性与反馈闭环

```
LLM 调用 ──► CostTracker.record(model, endpoint, tokens, latency)
                 │
                 ├─► 按 model/endpoint 聚合（进程内）
                 └─► db_usage_sink() ──► llm_usage 表

用户评分 ──► POST /api/v1/feedback/
                 │
                 ├─► rating < 4  →  label="bad"  （坏例）
                 ├─► message_feedback 表
                 └─► export_jsonl() ──► 交给人工标注 / SFT
```

## 9. 测试策略

```
tests/
├── fakes/fake_llm.py      FakeLLM：按脚本产出 content / tool_calls / error
├── unit/                  纯逻辑，零外部依赖
├── integration/           Agent Loop（无服务）· PostgreSQL · Qdrant
└── e2e/                   HTTP 冒烟
```

Agent Loop 是带外部依赖的异步状态机，换掉模型才能测。`FakeLLM` 预先编排每一轮的
返回，于是路由、迭代上限、并行工具调用、摘要触发、错误传播都能离线断言。

```python
llm = FakeLLM(script=[
    tool_step("skill_echo", {"text": "ping"}),   # 第一轮：要求调用工具
    content_step("回声完成"),                     # 第二轮：给出最终答案
])
```

**两个易踩的坑**（均已修复，见 `docs/testing-report.md`）：

1. pytest 会把**目录名**写进 `item.keywords`，用 `"integration" in item.keywords`
   判断会把 `tests/integration/` 下所有用例一并跳过；必须用 `item.get_closest_marker()`。
2. `get_engine()` 是进程级单例，asyncpg 连接绑定在首个事件循环上；pytest-asyncio
   每用例换新循环，因此集成测试要自建 `NullPool` 引擎。

## 10. 关键扩展点

| 想加什么 | 改哪里 |
|---|---|
| 新 LLM provider | `core/llm.py` 加一个新 Provider 类 |
| 新内置 Skill | `skills/builtin/<name>/SKILL.md` + `tools.py` |
| 新 MCP server | `mcp.servers.json` 加一项即可 |
| 新 RAG loader | `rag/ingest.py` 加分支 |
| 新召回策略 | `eval/runner.py` 的 `STRATEGIES` 加一项，评测自动对比 |
| 新评测指标 | `eval/metrics/` 对应文件加函数 |
| 新 Prompt 版本 | `core/prompt_store.py` 的 `register()` |
| 新前端面板 | `components/` 加组件 |