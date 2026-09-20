# 在线评测报告（Agent 轨迹 / 生成质量）

- 生成时间：2026-09-20 22:35:09
- 模型：`deepseek-flash`
- 向量：`local`

## Agent 轨迹

| 指标 | 值 |
|---|---|
| `tasks` | 20.0 |
| `tool_selection_acc` | 0.6792 |
| `tool_selection_exact` | 0.45 |
| `avg_steps` | 2.85 |
| `max_steps` | 6.0 |
| `task_success_rate` | 0.8 （5 条声明了 must_contain） |

| 任务 | 期望工具 | 实际工具 | 命中 |
|---|---|---|---|
| t01 | skill_echo | skill_echo | ✅ |
| t02 | skill_echo | skill_echo | ✅ |
| t03 | skill_code_review | skill_code_review, mcp__filesystem__read_file, mcp__filesystem__list_directory, mcp__filesystem__list_directory, skill_code_review, mcp__filesystem__read_file | ❌ |
| t04 | skill_code_review | skill_code_review, mcp__filesystem__list_directory, mcp__filesystem__list_directory, mcp__filesystem__read_file, mcp__filesystem__list_directory, mcp__filesystem__list_directory | ❌ |
| t05 | rag_search | rag_search | ✅ |
| t06 | rag_search | rag_search | ✅ |
| t07 | skill_rag_qa | skill_rag_qa | ✅ |
| t08 | skill_rag_qa | skill_rag_qa, rag_search | ❌ |
| t09 | skill_git_status | skill_git_status, mcp__filesystem__list_directory, mcp__filesystem__list_directory | ❌ |
| t10 | skill_git_status | skill_git_status, mcp__filesystem__list_directory, mcp__filesystem__list_directory | ❌ |
| t11 | skill_web_search | skill_web_search, skill_web_search, mcp__fetch__fetch, mcp__fetch__fetch, rag_search, skill_rag_qa | ❌ |
| t12 | skill_web_search | skill_web_search, mcp__fetch__fetch, rag_search | ❌ |
| t13 | skill_project_init | skill_project_init, mcp__filesystem__list_directory, mcp__filesystem__list_directory, mcp__filesystem__read_file | ❌ |
| t14 | mcp__filesystem__read_file | mcp__filesystem__read_file, mcp__filesystem__list_directory, mcp__filesystem__read_file, mcp__filesystem__read_file | ❌ |
| t15 | mcp__filesystem__list_directory | mcp__filesystem__list_directory, mcp__filesystem__list_directory, mcp__filesystem__list_directory, mcp__filesystem__list_directory | ✅ |
| t16 | mcp__fetch__fetch | mcp__fetch__fetch | ✅ |
| t17 | rag_search, skill_rag_qa | rag_search, rag_search, rag_search, rag_search | ❌ |
| t18 | rag_search, skill_code_review | rag_search, mcp__filesystem__list_directory, mcp__filesystem__list_directory, rag_search, mcp__filesystem__read_file, skill_code_review | ❌ |
| t19 | （无） | （无） | ✅ |
| t20 | （无） | （无） | ✅ |

> 说明：MCP 工具在本次评测中只做声明、由 stub 执行（真实 MCP server 需要 npx 与联网安装）。
> 因此 `tool_selection_acc` 有意义，而 MCP 任务上的 `task_success_rate` 只反映 stub 回显，不等于真实文件被读取。
