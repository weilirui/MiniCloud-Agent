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
                      │  └─ /api/v1/mcp/servers                    │
                      │                                             │
                      │  ┌─────────────┐    ┌─────────────────────┐ │
                      │  │ PostgreSQL  │    │ Qdrant              │ │
                      │  │ (会话/消息) │    │ (embedding/记忆)    │ │
                      │  └─────────────┘    └─────────────────────┘ │
                      └─────────────────────────────────────────────┘
```

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

### 检索

```
query
   │
   ▼
embedding(query)
   │
   ▼
Qdrant search (top_k=5, score_threshold=0.7)
   │
   ▼
返回 [{text, source, score}, ...]
```

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

## 8. 关键扩展点

| 想加什么 | 改哪里 |
|---|---|
| 新 LLM provider | `core/llm.py` 加一个新 Provider 类 |
| 新内置 Skill | `skills/builtin/<name>/SKILL.md` + `tools.py` |
| 新 MCP server | `mcp.servers.json` 加一项即可 |
| 新 RAG loader | `rag/ingest.py` 加分支 |
| 新前端面板 | `components/` 加组件 |