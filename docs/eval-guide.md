# 检索评测指南

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

| 类别 | 指标 | 位置 |
|---|---|---|
| 检索 | `recall@k` `precision@k` `hit_rate@k` `MRR` `nDCG@5` | `eval/metrics/retrieval.py` |
| 生成 | `lexical_support`（离线）· `citation_rate` · `llm_faithfulness`（LLM-as-judge） | `eval/metrics/generation.py` |
| Agent | `tool_selection_acc` `tool_selection_exact` `task_success_rate` `avg_steps` | `eval/metrics/agent.py` |

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

python -m eval.runner                       # 离线：内存向量库 + HashingEmbedder，不需要任何服务
python -m eval.runner --backend qdrant      # 真实 Qdrant，但仍用离线 embedding
python -m eval.runner --backend qdrant --embedder openai   # 真实 Qdrant + 真实 embedding（产生费用）
python -m eval.runner --top-k 3 --chunk-size 200 --overlap 40
```

或在仓库根目录：`make eval` / `make eval-qdrant`

`--backend qdrant` 从宿主机跑时必须能解析到 Qdrant。`settings.qdrant_url` 默认是容器网络内的
`http://qdrant:6333`，在宿主机上不生效，所以 runner 用 `--qdrant-url` 显式指定，
默认取环境变量 `QDRANT_URL`，回退 `http://localhost:16333`：

```bash
QDRANT_URL=http://localhost:16333 python -m eval.runner --backend qdrant
```

输出：
- `eval/reports/eval_report.md` —— 人读的对比表（含相对基线的差值）
- `eval/reports/eval_report.json` —— 机器可读，便于画趋势图或做 CI 卡口

## 6. 最新结果（2026-09-20，两种后端均已验证）

12 篇文档 / 29 个文本块，50 条查询，top_k=5：

| 策略 | recall@1 | recall@3 | recall@5 | MRR | nDCG@5 |
|---|---|---|---|---|---|
| `vector`（基线） | 0.5000 | 0.7300 | 0.8100 | 0.6673 | 0.6973 |
| `hybrid` | 0.6100 (+0.1100) | 0.8700 (+0.1400) | 0.9500 (+0.1400) | 0.8047 (+0.1374) | 0.8405 (+0.1432) |
| `hybrid_mmr` | 0.6100 (+0.1100) | 0.8600 (+0.1300) | **0.9700 (+0.1600)** | **0.8053 (+0.1380)** | **0.8415 (+0.1442)** |

结论：混合检索 + MMR 相对纯向量基线，Recall@5 提升 19.8%（0.81 → 0.97），MRR 提升 20.7%。

**内存后端与真实 Qdrant 后端跑出的数字完全一致**（逐位相同），这本身是一次有意义的验证：
说明融合与重排逻辑与向量库实现解耦，换后端不会改变策略排序。

## 7. 这个数字的边界（重要）

上表的向量来自 `HashingEmbedder`（对词袋做固定种子的随机投影），不是语义模型：

- ✅ 可以回答"策略 A 是否优于策略 B"——同一套向量下比较是公平的
- ❌ 不能回答"我们系统的 Recall@5 是 0.97"——换真实 embedding 后绝对值会变

**要拿绝对数值对外汇报，必须跑 `--backend qdrant --embedder openai`。**
报告文件里已经自动带上这条说明。

需要注意：`--embedder openai` 会真正调用 embedding API 并按量计费，且结果依赖
`EMBEDDING_BASE_URL` / `EMBEDDING_API_KEY` / `OPENAI_API_KEY` 是否配置正确。
