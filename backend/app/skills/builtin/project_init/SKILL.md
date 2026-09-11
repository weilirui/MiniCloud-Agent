---
name: project_init
description: 扫描当前项目结构，生成项目说明书（类似 CLAUDE.md）
trigger: "/init"
---

# Project Init Skill

扫描当前目录的文件结构、关键配置文件，生成一份给 Agent 阅读的项目说明书。

输出包含：
- 项目名称与简介
- 技术栈
- 目录结构
- 常用命令
- 开发约定

类比 Claude Code 的 `CLAUDE.md` / `AGENTS.md`。