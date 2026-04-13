# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Optional

from synthadoc.skills.base import BaseSkill, ExtractedContent, SkillMeta
from synthadoc.skills.registry import build_registry_cache, parse_skill_md, SkillManifestError

logger = logging.getLogger(__name__)

_BUILTIN_SKILLS_DIR = Path(__file__).parent.parent / "skills"
_GLOBAL_SKILLS_DIR = Path.home() / ".synthadoc" / "skills"


class SkillNotFoundError(Exception):
    def __init__(self, source: str, available: list[str] = None):
        msg = f"[ERR-SKILL-001] No skill matched: {source!r}."
        if available:
            msg += f" Available: {', '.join(sorted(available))}"
        super().__init__(msg)


def _entry_point_skill_dirs() -> list[Path]:
    import importlib.metadata
    dirs = []
    for ep in importlib.metadata.entry_points(group="synthadoc.skills"):
        try:
            d = Path(ep.value)
            if d.is_dir() and (d / "SKILL.md").exists():
                dirs.append(d)
        except Exception:
            logger.warning("Bad entry point skill %s", ep.name, exc_info=True)
    return dirs


def _skill_dirs_in(base: Optional[Path]) -> list[Path]:
    if not base or not base.is_dir():
        return []
    return [d for d in sorted(base.iterdir())
            if d.is_dir() and (d / "SKILL.md").exists()]


def _import_class(script: Path, class_name: str) -> type:
    spec = importlib.util.spec_from_file_location(script.stem, script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cls = getattr(mod, class_name, None)
    if cls is None:
        raise ImportError(f"Class '{class_name}' not found in {script}")
    return cls


def _register(skill_dir: Path, registry: dict, override: bool) -> None:
    try:
        meta = parse_skill_md(skill_dir)
        if override or meta.name not in registry:
            registry[meta.name] = meta
    except Exception as exc:
        logger.warning("Skipping skill folder %s: %s", skill_dir, exc)


class SkillAgent:
    def __init__(
        self,
        wiki_root: Optional[Path] = None,
        extra_dirs: Optional[list[Path]] = None,
    ) -> None:
        self._registry: dict[str, SkillMeta] = {}
        self._loaded: dict[str, type[BaseSkill]] = {}
        self._build_registry(wiki_root, extra_dirs or [])

    def _build_registry(self, wiki_root: Optional[Path], extra_dirs: list[Path]) -> None:
        reg: dict[str, SkillMeta] = {}

        # Priority order: extra_dirs > wiki/skills > ~/.synthadoc/skills > entry points > built-ins
        for d in extra_dirs:
            for sd in _skill_dirs_in(d):
                _register(sd, reg, override=True)

        if wiki_root:
            for sd in _skill_dirs_in(wiki_root / "skills"):
                _register(sd, reg, override=True)

        for sd in _skill_dirs_in(_GLOBAL_SKILLS_DIR):
            _register(sd, reg, override=False)

        for sd in _entry_point_skill_dirs():
            _register(sd, reg, override=False)

        for sd in _skill_dirs_in(_BUILTIN_SKILLS_DIR):
            _register(sd, reg, override=False)

        self._registry = reg

        if wiki_root is not None:
            cache_path = wiki_root / ".synthadoc" / "skill_registry.json"
            all_dirs = (
                list(extra_dirs)
                + [wiki_root / "skills", _GLOBAL_SKILLS_DIR]
                + _entry_point_skill_dirs()
                + [_BUILTIN_SKILLS_DIR]
            )
            try:
                build_registry_cache(all_dirs, cache_path)
            except Exception:
                logger.debug("Could not write skill registry cache", exc_info=True)

    def list_skills(self) -> list[SkillMeta]:
        return list(self._registry.values())

    def detect_skill(self, source: str) -> SkillMeta:
        s = source.lower()
        is_url = s.startswith("http://") or s.startswith("https://")
        # Pass 1: extension/prefix match — takes priority over intent matching.
        # For HTTP/HTTPS sources only startswith is checked so that the url skill
        # (prefix "https://") always wins over extension-based skills (e.g. pdf,
        # docx) — a URL ending in ".pdf" must be fetched first, not opened as a
        # local file. Non-URL sources use both endswith and startswith as before.
        for meta in self._registry.values():
            for ext in meta.triggers.extensions:
                if is_url:
                    if s.startswith(ext):
                        return meta
                else:
                    if s.endswith(ext) or s.startswith(ext):
                        return meta
        # Pass 2: intent match
        for meta in self._registry.values():
            for intent in meta.triggers.intents:
                if intent in s:
                    return meta
        raise SkillNotFoundError(source, list(self._registry.keys()))

    def get_skill(self, name: str) -> BaseSkill:
        if name not in self._registry:
            raise SkillNotFoundError(name, list(self._registry.keys()))
        if name not in self._loaded:
            meta = self._registry[name]
            self._check_requires(meta)
            cls = _import_class(meta.skill_dir / meta.entry_script, meta.entry_class)
            self._loaded[name] = cls
        instance = self._loaded[name]()
        instance.skill_dir = self._registry[name].skill_dir
        return instance

    def _check_requires(self, meta: SkillMeta) -> None:
        import importlib.metadata
        for pkg in meta.requires:
            dist_name = pkg.split("[")[0]
            try:
                importlib.metadata.distribution(dist_name)
            except importlib.metadata.PackageNotFoundError:
                raise ImportError(
                    f"[ERR-SKILL-002] Skill '{meta.name}' requires '{pkg}' — run: pip install {pkg}"
                )

    async def extract(self, source: str) -> ExtractedContent:
        meta = self.detect_skill(source)
        return await self.get_skill(meta.name).extract(source)
