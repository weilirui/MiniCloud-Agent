# Skills 编写指南

每个 Skill 是一个目录，包含 `SKILL.md`（描述）+ 可选的 `tools.py`（执行逻辑）。

## 最小例子

```
backend/app/skills/builtin/echo/
├── SKILL.md
└── tools.py
```

### SKILL.md

```markdown
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

把用户的输入原样返回。
```

### tools.py

```python
from app.skills.base import Skill, SkillContext


class EchoSkill(Skill):
    name = "echo"
    description = "回显用户输入"

    async def invoke(self, ctx: SkillContext, text: str) -> str:
        return f"你说的是：{text}"
```

## 注册

`registry.py` 启动时扫描 `SKILLS_BUILTIN_DIR` 和 `SKILLS_USER_DIR`，
对每个含 `SKILL.md` 的子目录自动 import `tools.py` 并实例化。

## 自定义 Skill

把你的 Skill 目录放到 `data/skills/<name>/`，重启后端即可被加载。