---
name: web_search
description: 联网搜索最新信息
trigger: "/search"
parameters:
  - name: query
    type: string
    required: true
    description: "搜索关键词"
---

# Web Search Skill

通过 Tavily API 搜索互联网。需要环境变量 `TAVILY_API_KEY`。

返回搜索结果摘要 + 来源链接。