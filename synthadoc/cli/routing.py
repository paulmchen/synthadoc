# Copyright (c) 2026 William Johnason / axoviq.com
from __future__ import annotations
import re
from pathlib import Path
from typing import Optional

import typer

from synthadoc.core.routing import RoutingIndex

routing_app = typer.Typer(name="routing", help="Manage ROUTING.md — scoped query routing.")

_BRANCH_RE = re.compile(r"^##\s+(.+)$")
_SLUG_RE = re.compile(r"-\s*\[\[([^\]]+)\]\]")


def _paths(wiki_root: Optional[str]) -> tuple[Path, Path, Path]:
    """Return (root, routing_path, wiki_dir) from the --wiki-root option."""
    root = Path(wiki_root) if wiki_root else Path(".")
    return root, root / "ROUTING.md", root / "wiki"


@routing_app.command("init")
def routing_init(
    wiki_root: Optional[str] = typer.Option(None, "--wiki-root", help="Path to wiki root"),
) -> None:
    """Generate ROUTING.md from current index.md branch structure (run once)."""
    root, routing_path, wiki_dir = _paths(wiki_root)
    index = wiki_dir / "index.md"

    if routing_path.exists():
        typer.echo("ROUTING.md already exists. Delete it first to re-init.")
        raise typer.Exit(1)

    if not index.exists():
        typer.echo(f"index.md not found at {index}")
        raise typer.Exit(1)

    branches: dict[str, list[str]] = {}
    current = None
    for line in index.read_text(encoding="utf-8").splitlines():
        if m := _BRANCH_RE.match(line):
            name = m.group(1).strip()
            if name not in ("Index", "Recently Added"):
                current = name
                branches.setdefault(current, [])
        elif current:
            for m2 in _SLUG_RE.finditer(line):
                branches[current].append(m2.group(1).strip())

    ri = RoutingIndex(branches)
    ri.save(routing_path)
    total = sum(len(v) for v in branches.values())
    typer.echo(f"ROUTING.md created — {len(branches)} branches, {total} slugs.")


@routing_app.command("validate")
def routing_validate(
    wiki_root: Optional[str] = typer.Option(None, "--wiki-root"),
) -> None:
    """Report dangling slugs in ROUTING.md (dry run — no changes)."""
    _, routing_path, wiki_dir = _paths(wiki_root)

    ri = RoutingIndex.parse(routing_path)
    existing = {p.stem for p in wiki_dir.glob("*.md")} if wiki_dir.exists() else set()
    dangling = ri.validate(existing)

    if not dangling:
        typer.echo("ROUTING.md is clean — no dangling slugs.")
        return

    typer.echo(f"Dangling slugs in ROUTING.md ({len(dangling)}):")
    for branch, slug in dangling:
        typer.echo(f"  [{branch}]  [[{slug}]]")


@routing_app.command("clean")
def routing_clean(
    wiki_root: Optional[str] = typer.Option(None, "--wiki-root"),
) -> None:
    """Auto-remove dangling slugs from ROUTING.md."""
    _, routing_path, wiki_dir = _paths(wiki_root)

    ri = RoutingIndex.parse(routing_path)
    existing = {p.stem for p in wiki_dir.glob("*.md")} if wiki_dir.exists() else set()
    removed = ri.clean(existing)

    if not removed:
        typer.echo("ROUTING.md is clean — nothing to remove.")
        return

    ri.save(routing_path)
    typer.echo(f"Removed {len(removed)} dangling entries from ROUTING.md")
    for branch, slug in removed:
        typer.echo(f"  [{branch}]  [[{slug}]]")
    typer.echo("ROUTING.md updated.")
