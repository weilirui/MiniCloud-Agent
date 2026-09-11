---
name: rag_qa
description: 从已上传的知识库检索并回答
trigger: "/rag"
parameters:
  - name: query
    type: string
    required: true
    description: "检索问题"
---

# RAG Q&A Skill

调用 RAG 检索接口，检索最相关的文档片段，并用 LLM 总结为回答。

适用于：
- 长文档问答
- 项目内部知识检索
- 个人笔记回顾