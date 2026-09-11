"""SKILL.md loader with frontmatter support."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import frontmatter

from app.skills.base import Skill
from app.utils.logging import get_logger

logger = get_logger(__name__)


def load_skill_md(md_path: Path) -> dict[str, Any]:
    """Parse a SKILL.md file.

    Returns: {"name", "description", "trigger", "parameters", "body", "dir_path"}
    """
    post = frontmatter.load(str(md_path))
    meta = dict(post.metadata)
    return {
        "name": meta.get("name", md_path.parent.name),
        "description": meta.get("description", ""),
        "trigger": meta.get("trigger", f"/{meta.get('name', md_path.parent.name)}"),
        "parameters": meta.get("parameters", {"type": "object", "properties": {}}),
        "body": post.content,
        "dir_path": md_path.parent,
    }


def load_skill_module(dir_path: Path) -> Any | None:
    """Try to import tools.py from a skill directory.

    Returns the module or None if not found.
    """
    tools_path = dir_path / "tools.py"
    if not tools_path.exists():
        return None

    module_name = f"skill_{dir_path.name}_{id(dir_path)}"
    spec = importlib.util.spec_from_file_location(module_name, tools_path)
    if not spec or not spec.loader:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        logger.warning("skill_module_load_failed", path=str(tools_path), error=str(e))
        return None
    return module


def find_skill_class(module: Any) -> type[Skill] | None:
    """Find a Skill subclass in a module."""
    if module is None:
        return None
    for name in dir(module):
        obj = getattr(module, name)
        if (
            isinstance(obj, type)
            and issubclass(obj, Skill)
            and obj is not Skill
        ):
            return obj
    return None