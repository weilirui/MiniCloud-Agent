"""Prompt versioning and deterministic A/B assignment.

Prompts are the cheapest thing to change and the easiest thing to break, so
they get the same treatment as code: named versions, a default, a history and
an experiment switch. Assignment is a stable hash of the session id, so the
same conversation always lands on the same variant.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PromptVersion:
    """One immutable revision of a prompt template."""

    name: str
    version: str
    template: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def render(self, **kwargs: Any) -> str:
        """Render the template. Unknown placeholders are left untouched."""
        out = self.template
        for key, value in kwargs.items():
            out = out.replace("{" + key + "}", str(value))
        return out


@dataclass
class PromptExperiment:
    """Traffic split across variants, in percent (must sum to <= 100)."""

    name: str
    variants: list[tuple[str, int]]  # [(version, percent), ...]

    def validate(self) -> None:
        total = sum(p for _, p in self.variants)
        if total <= 0 or total > 100:
            raise ValueError(f"experiment {self.name}: variant percentages must sum to 1..100, got {total}")


class PromptStore:
    """Registry of prompt templates with JSON-file persistence."""

    def __init__(self, storage_dir: str | Path | None = None) -> None:
        self.storage_dir = Path(storage_dir) if storage_dir else None
        self._versions: dict[str, dict[str, PromptVersion]] = {}
        self._default: dict[str, str] = {}
        self._experiments: dict[str, PromptExperiment] = {}
        if self.storage_dir:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            self.load_all()

    # ---------- registration ----------

    def register(
        self,
        name: str,
        version: str,
        template: str,
        *,
        metadata: dict[str, Any] | None = None,
        set_default: bool = False,
    ) -> PromptVersion:
        pv = PromptVersion(name=name, version=version, template=template, metadata=metadata or {})
        bucket = self._versions.setdefault(name, {})
        is_new = version not in bucket
        bucket[version] = pv
        if set_default or name not in self._default or is_new is False:
            # first registration becomes default; later ones only if asked
            if set_default or name not in self._default:
                self._default[name] = version
        logger.info("prompt_registered", name=name, version=version, default=self._default.get(name))
        return pv

    def set_default(self, name: str, version: str) -> None:
        if version not in self._versions.get(name, {}):
            raise KeyError(f"unknown prompt version: {name}@{version}")
        self._default[name] = version

    def get(self, name: str, version: str | None = None) -> PromptVersion:
        versions = self._versions.get(name)
        if not versions:
            raise KeyError(f"unknown prompt: {name}")
        key = version or self._default.get(name) or sorted(versions)[0]
        if key not in versions:
            raise KeyError(f"unknown prompt version: {name}@{key}")
        return versions[key]

    def list_versions(self, name: str) -> list[str]:
        return sorted(self._versions.get(name, {}))

    def render(self, name: str, version: str | None = None, **kwargs: Any) -> str:
        return self.get(name, version).render(**kwargs)

    # ---------- experiments ----------

    def set_experiment(self, experiment: PromptExperiment) -> None:
        experiment.validate()
        self._experiments[experiment.name] = experiment

    def get_experiment(self, name: str) -> PromptExperiment | None:
        return self._experiments.get(name)

    @staticmethod
    def _bucket(name: str, session_id: str) -> int:
        digest = hashlib.md5(f"{name}:{session_id}".encode("utf-8")).hexdigest()
        return int(digest[:8], 16) % 100

    def assign(self, name: str, session_id: str) -> str:
        """Deterministically pick a variant for ``session_id`` (0..99 bucket)."""
        experiment = self._experiments.get(name)
        if not experiment:
            return self._default.get(name, "v1")

        cursor = 0
        bucket = self._bucket(name, session_id)
        for version, percent in experiment.variants:
            cursor += percent
            if bucket < cursor:
                return version
        return self._default.get(name, experiment.variants[0][0])

    def render_for_session(
        self, name: str, session_id: str, **kwargs: Any
    ) -> tuple[str, str]:
        """Render for a session, honouring the experiment. Returns ``(text, version)``."""
        version = self.assign(name, session_id)
        return self.render(name, version, **kwargs), version

    # ---------- persistence ----------

    def _path_for(self, name: str) -> Path:
        assert self.storage_dir is not None
        return self.storage_dir / f"{name}.json"

    def save(self, name: str) -> None:
        if not self.storage_dir:
            return
        payload = {
            "name": name,
            "default": self._default.get(name),
            "versions": [asdict(v) for v in self._versions.get(name, {}).values()],
        }
        self._path_for(name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def load_all(self) -> None:
        if not self.storage_dir or not self.storage_dir.exists():
            return
        for path in sorted(self.storage_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:  # pragma: no cover - corrupt file
                logger.warning("prompt_load_failed", path=str(path), error=str(exc))
                continue
            name = payload.get("name") or path.stem
            for item in payload.get("versions", []):
                pv = PromptVersion(**item)
                self._versions.setdefault(name, {})[pv.version] = pv
            if payload.get("default"):
                self._default[name] = payload["default"]
