# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2026 Paul Chen / axoviq.com
# Plugin interface — third-party skills may extend these base classes under any licence.
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Triggers:
    extensions: list[str] = field(default_factory=list)
    intents: list[str] = field(default_factory=list)


@dataclass
class SkillMeta:
    name: str
    description: str
    # New structured fields
    version: str = "1.0"
    entry_script: str = "scripts/main.py"
    entry_class: str = ""
    triggers: Optional[Triggers] = None
    requires: list[str] = field(default_factory=list)
    skill_dir: Optional[Path] = None
    # Deprecated: kept for backwards compat with old flat-file skill classes
    extensions: list[str] = field(default_factory=list)

    def __post_init__(self):
        if self.triggers is None:
            self.triggers = Triggers(extensions=list(self.extensions), intents=[])
        if not self.entry_class:
            self.entry_class = "".join(p.title() for p in self.name.split("_")) + "Skill"


@dataclass
class ExtractedContent:
    text: str
    source_path: str
    metadata: dict = field(default_factory=dict)


class BaseSkill(ABC):
    skill_dir: Optional[Path] = None
    _resources_dir: Optional[Path] = None  # deprecated; use skill_dir

    def __init__(self):
        self._resource_cache: dict[str, str] = {}

    def get_resource(self, name: str) -> str:
        """Tier 3: search assets/ then references/ lazily. Falls back to _resources_dir."""
        if name in self._resource_cache:
            return self._resource_cache[name]
        # New folder-based lookup
        if self.skill_dir is not None:
            for subdir in ("assets", "references"):
                candidate = self.skill_dir / subdir / name
                if candidate.exists():
                    self._resource_cache[name] = candidate.read_text(encoding="utf-8")
                    return self._resource_cache[name]
        # Legacy fallback for old-style skills using _resources_dir
        if self._resources_dir is not None:
            legacy = self._resources_dir / name
            if legacy.exists():
                self._resource_cache[name] = legacy.read_text(encoding="utf-8")
                return self._resource_cache[name]
        raise FileNotFoundError(
            f"Resource '{name}' not found in assets/, references/, or resources/ "
            f"(skill_dir={self.skill_dir})"
        )

    @abstractmethod
    async def extract(self, source: str) -> ExtractedContent: ...
