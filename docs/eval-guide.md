# 评测指南

## 1. 为什么要单独做一个评测模块

"实现了 RAG" 和 "RAG 效果是多少" 是两件事。没有黄金集和指标，任何优化都只是自我感觉。
`backend/eval/` 把三件事固化下来：**可复现的数据集、可计算的指标、可对比的策略**。

## 2. 数据集

| 文件 | 内容 |
|---|---|
| `eval/datasets/corpus.jsonl` | 12 篇项目语料（RAG、分块、Skills、MCP、上下文、Agent 循环、持久化、部署、API、前端、测试、可观测性） |
| `eval/datasets/queries.jsonl` | 50 条查询，每条标注目标文档与关键词 |
| `eval/datasets/golden_retrieval.jsonl` | 50 条查询对应的相关文本块 id（**由脚本生成，不手写**） |
| `eval/datasets/agent_tasks.jsonl` | 20 条 Agent 任务，标注期望工具链 |

黄金集是**推导出来的**，不是拍脑袋标的：每条查询指定目标文档和关键词，脚本切分语料后，
取该文档中命中关键词最多的文本块作为相关块。语料或切分参数一变，重新生成即可：

```bash
cd backend
python scripts/build_golden_dataset.py
# corpus docs: 12 / chunks: 29 / queries: 50 / keyword-matched: 50
```

## 3. 指标

| 类别 | 指标 | 位置 | 需要 LLM |
|---|---|---|---|
| 检索 | `recall@k` `precision@k` `hit_rate@k` `MRR` `nDCG@5` | `eval/metrics/retrieval.py` | 否 |
| 生成 | `lexical_support` · `citation_rate` | `eval/metrics/generation.py` | 否 |
| 生成 | `llm_faithfulness`（LLM-as-judge） | `eval/metrics/generation.py` | 是 |
| Agent | `tool_selection_acc` `tool_selection_exact` `task_success_rate` `avg_steps` | `eval/metrics/agent.py` | 是 |

## 4. 三种检索策略

| 策略 | 组成 |
|---|---|
| `vector` | 纯向量召回（项目原本的实现，作为基线） |
| `hybrid` | 向量 + BM25，归一化加权融合 |
| `hybrid_mmr` | 向量 + BM25 + MMR 多样性重排 |

MMR 的相关性-冗余度权衡用**词元 Jaccard** 计算，不额外调用 embedding，零成本。

## 5. 运行

```bash
cd backend

# --- 检索评测 ---
python -m eval.runner                          # 哈希向量：只用于策略间相对比较
python -m eval.runner --embedder local         # 本地语义模型 bge-small-zh（免费，可作绝对数值）
python -m eval.runner --backend qdrant --embedder local
python -m eval.runner --embedder openai        # 托管 embedding API（产生费用）

# --- 在线评测（需要真实 LLM）---
python -m eval.online_runner --suite agent       # Agent 工具选择，20 条任务
python -m eval.online_runner --suite generation  # 生成 groundedness，50 条查询
python -m eval.online_runner --suite all
```

或在仓库根目录：`make eval` / `make eval-semantic` / `make eval-qdrant` /
`make eval-agent` / `make eval-online`

`--embedder local` 首次运行会下载 `BAAI/bge-small-zh-v1.5`（约 55 MB，ONNX，CPU 推理），
缓存落在 `sys.prefix/fastembed_cache`，可用 `FASTEMBED_CACHE_DIR` 覆盖。
依赖是可选的：`pip install -e ".[eval]"`。

`--backend qdrant` 从宿主机跑时必须能解析到 Qdrant。`settings.qdrant_url` 默认是容器网络内的
`http://qdrant:6333`，在宿主机上不生效，所以 runner 用 `--qdrant-url` 显式指定，
默认取环境变量 `QDRANT_URL`，回退 `http://localhost:16333`：

```bash
QDRANT_URL=http://localhost:16333 python -m eval.runner --backend qdrant
```

输出：
- `eval/reports/eval_report.md` / `.json` —— 检索策略对比
- `eval/reports/online_eval_report.md` / `.json` —— Agent 轨迹与生成质量

## 6. 检索结果

12 篇文档 / 29 个文本块，50 条查询，top_k=5。同一份黄金集、两种向量来源各跑一次。

### 6.1 语义向量（bge-small-zh-v1.5）— **这组是可对外说的绝对数值**

| 策略 | recall@1 | recall@3 | recall@5 | MRR | nDCG@5 |
|---|---|---|---|---|---|
| `vector`（基线） | 0.6800 | 0.9000 | 0.9300 | 0.8473 | 0.8635 |
| `hybrid` | 0.7600 | 0.9500 | **0.9700** | **0.9083** | **0.9200** |
| `hybrid_mmr` | 0.7600 | 0.9500 | **0.9700** | **0.9083** | **0.9200** |

Recall@5 +4.3%（0.93 → 0.97），MRR +7.2%（0.8473 → 0.9083），nDCG@5 +6.5%。

### 6.2 哈希向量（HashingEmbedder）— 只能相对比较

| 策略 | recall@1 | recall@3 | recall@5 | MRR | nDCG@5 |
|---|---|---|---|---|---|
| `vector`（基线） | 0.5000 | 0.7300 | 0.8100 | 0.6673 | 0.6973 |
| `hybrid` | 0.6100 | 0.8700 | 0.9500 | 0.8047 | 0.8405 |
| `hybrid_mmr` | 0.6100 | 0.8600 | **0.9700** | **0.8053** | **0.8415** |

Recall@5 +19.8%，MRR +20.7%。

### 6.3 两组数字为什么差这么多（重要）

**哈希向量把基线压得偏低，从而放大了优化幅度。** HashingEmbedder 是词袋的随机投影，
没有语义，纯向量召回在这个语料上只能到 0.81；换成真实语义模型后基线直接是 0.93，
留给混合检索的空间只剩 0.04。

所以：

- 想说"我们的检索质量是多少" → 用 6.1（0.93 → 0.97）
- 想说"混合检索确实有效" → 两组都成立，但 6.1 的 +4.3% 是保守且可信的下界
- ❌ 不要拿 6.2 的 +19.8% 去暗示绝对质量提升，那是评测设置的产物

内存后端与真实 Qdrant 后端跑出的数字**逐位相同**，这本身是一次有意义的验证：
融合与重排逻辑与向量库实现解耦，换后端不改变策略排序。

## 7. Agent 与生成质量结果（deepseek-flash，2026-09-20）

### Agent 轨迹（20 条任务）

| 指标 | 值 |
|---|---|
| `tool_selection_acc` | 0.6792 |
| `tool_selection_exact` | 0.4500 |
| `task_success_rate` | 0.8000（20 条中仅 5 条声明了 `must_contain`） |
| `avg_steps` | 2.85 |
| `max_steps` | 6 |

逐条明细见 `eval/reports/online_eval_report.md`。**结果暴露了一个真实问题**：模型倾向于
冗余调用工具——`t03` 只是"审查 agent.py"，实际却触发了 6 次工具调用（其中 5 次是
`mcp__filesystem__*`），直接打满迭代上限。无工具任务（t19/t20）反而全对。

这个数字不好看，但它正是评测模块存在的意义：没有这套东西，冗余调用只会被当成"模型比较积极"。

### 生成质量（50 条查询）

| 指标 | 值 |
|---|---|
| `lexical_support` | 0.8011 |
| `citation_rate` | 0.9800 |

约 80% 的回答词元能在召回材料中找到依据，98% 的回答带 `[来源 N]` 引用。

### 这组数字的边界

- MCP 工具在评测中**只声明、由 stub 执行**（真实 MCP server 需要 npx 与联网安装）。
  所以 `tool_selection_acc` 有意义，而 MCP 任务上的 `task_success_rate` 只反映 stub 回显，
  不等于真实文件被读取。Skills 与 RAG 走的是真实实现。
- `task_success_rate` 只统计声明了 `must_contain` 的任务。把"没声明"算成失败会让这个
  指标变成在数"有多少条任务写了断言"，与 Agent 能力无关。
- 生成质量用的是 `lexical_support`（词元覆盖）而非 LLM-as-judge：便宜、确定、可复现，
  但只能衡量"有没有依据"，衡量不了"有没有答对"。
