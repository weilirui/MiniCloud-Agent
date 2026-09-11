---
name: echo
description: 回显用户输入，用于验证系统是否正常
trigger: "/echo"
parameters:
  - name: text
    type: string
    required: true
---

# Echo Skill

把用户的输入原样返回。用于调试和验证 Agent 工具调用链路是否通畅。