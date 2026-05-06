# Copyright (c) 2026 William Johnason / axoviq.com
from __future__ import annotations
import re
from pathlib import Path

_BRANCH_RE = re.compile(r"^##\s+(.+)$")
_SLUG_RE = re.compile(r"^\s*-\s*\[\[([^\]]+)\]\]")


class RoutingIndex:
    def __init__(self, branches: dict[str, list[str]]) -> None:
        self.branches = branches

    @classmethod
    def parse(cls, path: Path) -> "RoutingIndex":
        if not path.exists():
            return cls({})
        branches: dict[str, list[str]] = {}
        current: str | None = None
        for line in path.read_text(encoding="utf-8").splitlines():
            if m := _BRANCH_RE.match(line):
                current = m.group(1).strip()
                branches.setdefault(current, [])
            elif current and (m := _SLUG_RE.match(line)):
                branches[current].append(m.group(1).strip())
        return cls(branches)

    def validate(self, existing_slugs: set[str]) -> list[tuple[str, str]]:
        dangling = []
        for branch, slugs in self.branches.items():
            for slug in slugs:
                if slug not in existing_slugs:
                    dangling.append((branch, slug))
        return dangling

    def clean(self, existing_slugs: set[str]) -> list[tuple[str, str]]:
        removed = []
        for branch in list(self.branches):
            kept = []
            for slug in self.branches[branch]:
                if slug in existing_slugs:
                    kept.append(slug)
                else:
                    removed.append((branch, slug))
            self.branches[branch] = kept
        return removed

    def add_slug(self, slug: str, branch: str) -> None:
        self.branches.setdefault(branch, [])
        if slug not in self.branches[branch]:
            self.branches[branch].append(slug)

    def slugs_for_branches(self, branch_names: list[str]) -> list[str]:
        result = []
        for b in branch_names:
            result.extend(self.branches.get(b, []))
        return result

    def save(self, path: Path) -> None:
        lines = []
        for branch, slugs in self.branches.items():
            lines.append(f"## {branch}")
            for slug in slugs:
                lines.append(f"- [[{slug}]]")
            lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")
