# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import json
import logging
from pathlib import Path

import yaml

from synthadoc.skills.base import SkillMeta, Triggers

logger = logging.getLogger(__name__)

_REQUIRED = {"name", "version", "description", "entry", "triggers"}
_CACHE_VERSION = 1


class SkillManifestError(ValueError):
    pass


def parse_skill_md(skill_dir: Path) -> SkillMeta:
    """Parse SKILL.md frontmatter only. Never reads the body."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        raise SkillManifestError(f"SKILL.md not found in {skill_dir}")
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise SkillManifestError(f"{skill_md}: must begin with YAML frontmatter (---)")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise SkillManifestError(f"{skill_md}: unterminated frontmatter block")
    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as exc:
        raise SkillManifestError(f"{skill_md}: invalid YAML — {exc}") from exc
    missing = _REQUIRED - fm.keys()
    if missing:
        raise SkillManifestError(
            f"{skill_md}: missing required field(s): {', '.join(sorted(missing))}"
        )
    entry = fm["entry"]
    t = fm.get("triggers", {})
    return SkillMeta(
        name=fm["name"],
        version=str(fm.get("version", "1.0")),
        description=fm["description"],
        entry_script=entry.get("script", "scripts/main.py"),
        entry_class=entry.get("class", ""),
        triggers=Triggers(
            extensions=t.get("extensions", []),
            intents=t.get("intents", []),
        ),
        requires=fm.get("requires") or [],
        skill_dir=skill_dir,
    )


def _discover_skill_dirs(search_dirs: list[Path]) -> list[Path]:
    found = []
    for base in search_dirs:
        if not base or not base.is_dir():
            continue
        for d in sorted(base.iterdir()):
            if d.is_dir() and (d / "SKILL.md").exists():
                found.append(d)
    return found


def _load_cache(cache_path: Path) -> dict:
    if not cache_path.exists():
        return {}
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        if data.get("version") != _CACHE_VERSION:
            return {}
        return data.get("entries", {})
    except Exception:
        return {}


def _serialise(meta: SkillMeta) -> dict:
    skill_md = meta.skill_dir / "SKILL.md"
    return {
        "skill_dir": str(meta.skill_dir),
        "skill_md_mtime": skill_md.stat().st_mtime if skill_md.exists() else 0.0,
        "name": meta.name, "version": meta.version, "description": meta.description,
        "entry": {"script": meta.entry_script, "class": meta.entry_class},
        "triggers": {"extensions": meta.triggers.extensions, "intents": meta.triggers.intents},
        "requires": meta.requires,
    }


def _deserialise(e: dict) -> SkillMeta:
    return SkillMeta(
        name=e["name"], version=e["version"], description=e["description"],
        entry_script=e["entry"]["script"], entry_class=e["entry"]["class"],
        triggers=Triggers(extensions=e["triggers"]["extensions"],
                          intents=e["triggers"]["intents"]),
        requires=e.get("requires", []),
        skill_dir=Path(e["skill_dir"]),
    )


def _write_cache(cache_path: Path, registry: dict[str, SkillMeta]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps({"version": _CACHE_VERSION,
                    "entries": {n: _serialise(m) for n, m in registry.items()}},
                   indent=2),
        encoding="utf-8",
    )


def build_registry_cache(
    skill_dirs: list[Path],
    cache_path: Path,
) -> dict[str, SkillMeta]:
    """Scan skill_dirs, load or re-parse each SKILL.md, write cache if changed."""
    cached = _load_cache(cache_path)
    registry: dict[str, SkillMeta] = {}
    changed = False

    for skill_dir in _discover_skill_dirs(skill_dirs):
        skill_md = skill_dir / "SKILL.md"
        mtime = skill_md.stat().st_mtime if skill_md.exists() else 0.0
        name_guess = skill_dir.name
        ce = cached.get(name_guess)

        if ce and ce.get("skill_dir") == str(skill_dir) and ce.get("skill_md_mtime") == mtime:
            try:
                meta = _deserialise(ce)
                registry[meta.name] = meta
                continue
            except Exception:
                pass

        # Parse fresh
        try:
            meta = parse_skill_md(skill_dir)
            registry[meta.name] = meta
            changed = True
        except SkillManifestError as exc:
            logger.warning("Skipping %s: %s", skill_dir, exc)

    # Detect deletions
    if not changed:
        for name in cached:
            if name not in registry:
                changed = True
                break

    if changed:
        _write_cache(cache_path, registry)

    return registry
