# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import re
import yaml
from pathlib import Path

import typer

from synthadoc.cli.main import app
from synthadoc.cli._http import post

_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
_SKIP_SLUGS = {"index", "log", "dashboard", "purpose"}


def _parse_frontmatter(text: str) -> dict:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}


def _index_suggestion(slug: str, fm: dict) -> str:
    title = fm.get("title") or slug.replace("-", " ").title()
    tags = fm.get("tags") or []
    if isinstance(tags, list) and tags:
        hint = ", ".join(str(t) for t in tags[:4])
    else:
        hint = title
    return f"- [[{slug}]] — {hint}"

lint_app = typer.Typer(help="Lint the wiki for contradictions and orphans.")
app.add_typer(lint_app, name="lint")


@lint_app.command("run")
def lint_cmd(
    scope: str = typer.Option("all", "--scope", help="all/contradictions/orphans/stale"),
    auto_resolve: bool = typer.Option(False, "--auto-resolve"),
    wiki: str = typer.Option(".", "--wiki", "-w"),
):
    """Enqueue a lint job. Requires synthadoc serve to be running."""
    result = post(wiki, "/jobs/lint", {"scope": scope, "auto_resolve": auto_resolve})
    typer.echo(f"Lint enqueued -> job {result['job_id']}")
    typer.echo(f"Check status: synthadoc jobs status {result['job_id']} -w {wiki}")
    typer.echo(f"View results: synthadoc lint report -w {wiki}")


@lint_app.command("report")
def lint_report(
    wiki: str = typer.Option(".", "--wiki", "-w"),
):
    """Show current contradictions and orphan pages — no server required.

    Reads wiki files directly. Run after 'synthadoc lint' completes to see
    what needs your attention.
    """
    from synthadoc.cli.install import resolve_wiki_path

    wiki_dir = resolve_wiki_path(wiki) / "wiki"
    if not wiki_dir.exists():
        from synthadoc import errors as E
        E.cli_error(E.WIKI_NOT_FOUND, f"Wiki directory not found: {wiki_dir}")

    pages = list(wiki_dir.glob("*.md"))

    # --- Contradictions ---
    contradicted = []
    for p in pages:
        if p.stem in _SKIP_SLUGS:
            continue
        raw = p.read_text(encoding="utf-8")
        if "status: contradicted" in raw:
            contradicted.append(p.stem)

    # --- Orphans: pages with no inbound [[wikilinks]] from any other page ---
    referenced: set[str] = set()
    page_texts: dict[str, str] = {}
    for p in pages:
        raw = p.read_text(encoding="utf-8")
        page_texts[p.stem] = raw
        for link in _WIKILINK_RE.findall(raw):
            slug_part = link.split("|")[0].strip()
            referenced.add(slug_part.lower().replace(" ", "-"))

    orphans = [
        p.stem for p in pages
        if p.stem not in referenced and p.stem not in _SKIP_SLUGS
    ]

    # --- Report ---
    has_issues = contradicted or orphans
    if not has_issues:
        typer.echo("All clear — no contradictions or orphan pages found.")
        return

    if contradicted:
        typer.echo(f"\nContradicted pages ({len(contradicted)}) - need review:\n")
        for slug in contradicted:
            typer.echo(f"  {slug}")
            typer.echo(f"    -> Open wiki/{slug}.md, resolve the conflict, then set status: active")
            typer.echo(f"    -> Or re-run: synthadoc lint -w {wiki} --auto-resolve")

    if orphans:
        typer.echo(f"\nOrphan pages ({len(orphans)}) - no inbound links:\n")
        for slug in orphans:
            fm = _parse_frontmatter(page_texts.get(slug, ""))
            suggestion = _index_suggestion(slug, fm)
            typer.echo(f"  {slug}")
            typer.echo(f"    -> Add [[{slug}]] to a related page, or add to wiki/index.md:")
            typer.echo(f"         {suggestion}")

    typer.echo(
        f"\n{len(contradicted)} contradiction(s), {len(orphans)} orphan(s) found."
        f"\nDashboard: open wiki/dashboard.md in Obsidian for a live view."
    )
