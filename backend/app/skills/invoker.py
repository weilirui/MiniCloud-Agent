"""Skill invocation dispatcher.

Handles explicit /command style invocations and dispatches to skills.
"""

from __future__ import annotations

import re

from app.skills.base import Skill, SkillContext
from app.skills.registry import SkillsRegistry, get_registry
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Match `/<command> <args...>` at start of message
COMMAND_RE = re.compile(r"^/([a-zA-Z0-9_\-]+)\s*(.*)$", re.DOTALL)


def detect_slash_command(message: str) -> tuple[str, str] | None:
    """Detect a slash command at the start of a message.

    Returns: (command, remainder) or None.
    """
    m = COMMAND_RE.match(message.strip())
    if not m:
        return None
    return m.group(1), m.group(2).strip()


def find_skill_for_command(registry: SkillsRegistry, command: str) -> Skill | None:
    """Find a skill by trigger command.

    Match by trigger (e.g. "/code-review") or by name.
    """
    # Try by trigger: "/code-review"
    for s in registry.list():
        if s.trigger == f"/{command}":
            return s
    # Try by name
    return registry.get(command)


def parse_args(skill: Skill, raw: str) -> dict:
    """Parse raw args string into a dict matching skill.parameters.

    Supports:
    - JSON: `{...}`
    - key=value pairs
    - positional args by parameter order
    """
    raw = raw.strip()
    if not raw:
        return {}

    if raw.startswith("{"):
        try:
            import json
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

    # key=value pairs
    if "=" in raw:
        result = {}
        # naive splitter, respects quotes
        parts = re.findall(r'(\w+)=("[^"]*"|\'[^\']*\'|\S+)', raw)
        for k, v in parts:
            v = v.strip("'\"")
            result[k] = v
        if result:
            return result

    # positional: pass as first param
    params = skill.parameters.get("properties", {})
    if params:
        first_param = next(iter(params), None)
        if first_param:
            return {first_param: raw}

    return {}


async def invoke_skill(
    name_or_trigger: str,
    raw_args: str,
    ctx: SkillContext,
    registry: SkillsRegistry | None = None,
) -> str:
    """Invoke a skill by name or trigger."""
    registry = registry or get_registry()
    skill = find_skill_for_command(registry, name_or_trigger)
    if not skill:
        raise ValueError(f"skill not found: {name_or_trigger}")

    args = parse_args(skill, raw_args)
    logger.info("skill_invoking", skill=skill.name, args=args)
    return await skill.invoke(ctx, **args)