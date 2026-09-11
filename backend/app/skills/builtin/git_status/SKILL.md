---
name: git_status
description: 查看 git 状态 + 最近提交 + 总结当前分支变化
trigger: "/git"
parameters:
  - name: detail
    type: boolean
    required: false
    description: "是否包含详细 diff（默认 false）"
---

# Git Status Skill

执行 `git status`、`git log --oneline -10`、`git diff --stat`，用 LLM 总结：

- 当前分支
- 是否有未提交变更
- 最近几次提交
- 主要变更文件

只读操作。