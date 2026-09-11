---
name: code_review
description: 对指定文件做代码审查，输出改进建议
trigger: "/code-review"
parameters:
  - name: path
    type: string
    required: true
    description: "要审查的文件路径（项目内相对路径）"
---

# Code Review Skill

读取指定文件，使用 LLM 进行代码审查并输出结构化建议。

## 输出

- 总体评价（1-2 句）
- 优点
- 问题（按严重程度排序）
- 改进建议（带代码示例）

只读操作，不修改任何文件。