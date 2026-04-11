# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from synthadoc.skills.base import BaseSkill, ExtractedContent, SkillMeta

logger = logging.getLogger(__name__)


class SkillNotFoundError(Exception):
    pass


class SkillAgent:
    def __init__(self, extra_dirs: Optional[list[Path]] = None) -> None:
        self._registry: dict[str, type[BaseSkill]] = {}
        self._load_builtins()
        self._load_entry_points()
        for d in (extra_dirs or []):
            self._load_local_dir(Path(d))

    def _load_builtins(self) -> None:
        from synthadoc.skills.pdf.scripts.main import PdfSkill
        from synthadoc.skills.url.scripts.main import UrlSkill
        from synthadoc.skills.markdown.scripts.main import MarkdownSkill
        from synthadoc.skills.docx.scripts.main import DocxSkill
        from synthadoc.skills.xlsx.scripts.main import XlsxSkill
        from synthadoc.skills.image.scripts.main import ImageSkill
        for cls in (PdfSkill, UrlSkill, MarkdownSkill, DocxSkill, XlsxSkill, ImageSkill):
            self._registry[cls.meta.name] = cls

    def _load_entry_points(self) -> None:
        import importlib.metadata
        for ep in importlib.metadata.entry_points(group="synthadoc.skills"):
            try:
                cls = ep.load()
                if isinstance(cls, type) and issubclass(cls, BaseSkill) and cls is not BaseSkill:
                    self._registry[cls.meta.name] = cls
            except Exception:
                logger.warning("Failed to load pip skill entry point %s", ep.name, exc_info=True)

    def _load_local_dir(self, directory: Path) -> None:
        import importlib.util
        for py_file in sorted(directory.glob("*.py")):
            try:
                spec = importlib.util.spec_from_file_location(py_file.stem, py_file)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                loaded_any = False
                for attr in vars(mod).values():
                    if (isinstance(attr, type) and issubclass(attr, BaseSkill)
                            and attr is not BaseSkill):
                        resources_dir = py_file.parent / "resources"
                        attr._resources_dir = resources_dir if resources_dir.exists() else None
                        self._registry[attr.meta.name] = attr
                        loaded_any = True
                if not loaded_any:
                    logger.warning("No BaseSkill subclass found in %s — skipped", py_file)
            except Exception:
                logger.warning("Failed to load local skill from %s", py_file, exc_info=True)

    def list_skills(self) -> list[SkillMeta]:
        """Tier 1: metadata only, always available."""
        return [cls.meta for cls in self._registry.values()]

    def detect_skill(self, source: str) -> SkillMeta:
        source_lower = source.lower()
        for cls in self._registry.values():
            for ext in cls.meta.extensions:
                if source_lower.endswith(ext) or source_lower.startswith(ext):
                    return cls.meta
        raise SkillNotFoundError(f"No skill for: {source}")

    def get_skill(self, name: str) -> BaseSkill:
        """Tier 2: instantiate skill body."""
        if name not in self._registry:
            raise SkillNotFoundError(f"Skill not found: {name}")
        return self._registry[name]()

    async def extract(self, source: str) -> ExtractedContent:
        meta = self.detect_skill(source)
        return await self.get_skill(meta.name).extract(source)
