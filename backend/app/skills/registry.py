"""Skills registry: scan builtin + user dirs, instantiate all Skills."""

from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.skills.base import Skill
from app.skills.loader import (
    find_skill_class,
    load_skill_md,
    load_skill_module,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)


class SkillsRegistry:
    """Registry of all available Skills."""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        if not skill.name:
            raise ValueError("skill.name required")
        self._skills[skill.name] = skill
        logger.info("skill_registered", name=skill.name)

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def list(self) -> list[Skill]:
        return list(self._skills.values())

    def scan_directory(self, directory: str | Path) -> None:
        """Scan a directory for SKILL.md files and register them."""
        directory = Path(directory)
        if not directory.exists():
            logger.debug("skills_dir_not_exist", path=str(directory))
            return

        for entry in sorted(directory.iterdir()):
            if not entry.is_dir():
                continue
            md_path = entry / "SKILL.md"
            if not md_path.exists():
                continue
            self._load_one(entry, md_path)

    def _load_one(self, dir_path: Path, md_path: Path) -> None:
        try:
            meta = load_skill_md(md_path)
        except Exception as e:
            logger.warning("skill_md_load_failed", path=str(md_path), error=str(e))
            return

        # Try to load a tools.py implementation
        module = load_skill_module(dir_path)
        cls = find_skill_class(module)

        if cls:
            try:
                skill = cls()
                # Allow SKILL.md to override metadata if implementation doesn't set it
                if not skill.description:
                    skill.description = meta["description"]
                if not skill.trigger:
                    skill.trigger = meta["trigger"]
                if not skill.parameters or not skill.parameters.get("properties"):
                    meta_params = meta.get("parameters")
                    # SKILL.md `parameters` may be a legacy list (e.g. `[]`) which is
                    # not a valid JSON Schema; only override with a proper object schema.
                    if isinstance(meta_params, dict) and meta_params.get("type") == "object":
                        skill.parameters = meta_params
                self.register(skill)
                return
            except Exception as e:
                logger.warning("skill_instantiate_failed", path=str(dir_path), error=str(e))

        # Fallback: create a metadata-only skill that returns the SKILL.md body
        fallback = _MetadataOnlySkill(
            name=meta["name"],
            description=meta["description"],
            trigger=meta["trigger"],
            parameters=meta["parameters"],
            body=meta["body"],
        )
        self.register(fallback)
        logger.info("skill_metadata_only", name=meta["name"])

    def info_list(self) -> list[dict]:
        return [s.info() for s in self.list()]


class _MetadataOnlySkill(Skill):
    """Skill that just returns the SKILL.md body. Used when no tools.py."""

    def __init__(self, name: str, description: str, trigger: str, parameters: dict, body: str):
        self.name = name
        self.description = description
        self.trigger = trigger
        self.parameters = parameters
        self._body = body

    async def invoke(self, ctx, **kwargs) -> str:
        return self._body


# Global registry, populated at app startup
_registry: SkillsRegistry | None = None


def init_registry() -> SkillsRegistry:
    """Create and populate the global registry."""
    global _registry
    if _registry is None:
        _registry = SkillsRegistry()
        _registry.scan_directory(settings.skills_builtin_dir)
        _registry.scan_directory(settings.skills_user_dir)
        logger.info("skills_registry_ready", count=len(_registry.list()))
    return _registry


def get_registry() -> SkillsRegistry:
    if _registry is None:
        return init_registry()
    return _registry