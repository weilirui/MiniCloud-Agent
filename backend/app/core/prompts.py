"""System prompt templates with Skills/MCP/tools injection."""

from __future__ import annotations


SYSTEM_PROMPT_TEMPLATE = """你是 minicloud-agent，一个轻量级的 AI Agent 平台助手。

## 当前时间
{current_time}

## 工作环境
- 操作系统: {os_info}
- 工作目录: {cwd}

## 可用 Skills（用户可用 `/<name>` 调用）
{skills_summary}

## 可用 MCP 工具（来自外部 MCP server）
{mcp_tools_summary}

## 内置工具
- `rag_search` —— 从知识库检索相关片段

## 行为准则
1. 优先调用合适的工具完成任务，而不是凭空猜测。
2. 涉及文件/网络/外部系统操作时，调用对应 Skill 或 MCP 工具。
3. 回答简洁准确，必要时给出代码示例。
4. 使用 Markdown 格式输出。
5. 中文回答，除非用户明确要求英文。
"""


SKILLS_SUMMARY_PLACEHOLDER = "（暂无）"
MCP_TOOLS_SUMMARY_PLACEHOLDER = "（暂无）"


def build_system_prompt(
    *,
    current_time: str,
    os_info: str,
    cwd: str,
    skills_summary: str = SKILLS_SUMMARY_PLACEHOLDER,
    mcp_tools_summary: str = MCP_TOOLS_SUMMARY_PLACEHOLDER,
) -> str:
    """Build the system prompt with dynamic context."""
    return SYSTEM_PROMPT_TEMPLATE.format(
        current_time=current_time,
        os_info=os_info,
        cwd=cwd,
        skills_summary=skills_summary,
        mcp_tools_summary=mcp_tools_summary,
    )


def build_skills_summary(skills: list[dict]) -> str:
    """Build a human-readable summary of available skills."""
    if not skills:
        return SKILLS_SUMMARY_PLACEHOLDER

    lines = []
    for s in skills:
        trigger = s.get("trigger", f"/{s.get('name')}")
        desc = s.get("description", "")
        lines.append(f"- `{trigger}` —— {desc}")
    return "\n".join(lines)


def build_mcp_tools_summary(tools: list[dict]) -> str:
    """Build a human-readable summary of MCP tools."""
    if not tools:
        return MCP_TOOLS_SUMMARY_PLACEHOLDER

    lines = []
    for t in tools:
        server = t.get("server", "mcp")
        name = t.get("name", "")
        desc = t.get("description", "")
        lines.append(f"- `mcp__{server}__{name}` —— {desc}")
    return "\n".join(lines)