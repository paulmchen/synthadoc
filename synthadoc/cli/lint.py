# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import re
import yaml
from pathlib import Path

import typer

from synthadoc.cli.main import app
from synthadoc.cli._http import post

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
from synthadoc.agents.lint_agent import find_orphan_slugs, LINT_SKIP_SLUGS


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

def _sync_orphan_frontmatter(
    wiki_dir: Path,
    page_texts: dict[str, str],
    orphan_set: set[str],
) -> None:
    """Write orphan: true/false into page frontmatter so the Obsidian dashboard
    (WHERE orphan = true) stays in sync with what lint report just computed."""
    from synthadoc.agents.lint_agent import LINT_SKIP_SLUGS
    for slug, text in page_texts.items():
        if slug in LINT_SKIP_SLUGS:
            continue
        fm = _parse_frontmatter(text)
        desired = slug in orphan_set
        if fm.get("orphan", False) == desired:
            continue  # already correct — skip to avoid unnecessary disk write
        # Rewrite only the orphan key in the frontmatter block
        path = wiki_dir / f"{slug}.md"
        m = _FRONTMATTER_RE.match(text)
        if not m:
            continue
        try:
            fm_data = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            continue
        fm_data["orphan"] = desired
        new_fm = yaml.dump(fm_data, default_flow_style=False, allow_unicode=True).rstrip()
        new_text = f"---\n{new_fm}\n---" + text[m.end():]
        path.write_text(new_text, encoding="utf-8")


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

    page_texts: dict[str, str] = {p.stem: p.read_text(encoding="utf-8") for p in pages}

    # --- Contradictions ---
    contradicted = [
        stem for stem, text in page_texts.items()
        if stem not in LINT_SKIP_SLUGS and "status: contradicted" in text
    ]

    # --- Orphans ---
    # Strip frontmatter before scanning so CLI and server-side LintAgent use the
    # same definition: only wikilinks in the page body count as real references.
    page_bodies: dict[str, str] = {
        slug: (text[m.end():] if (m := _FRONTMATTER_RE.match(text)) else text)
        for slug, text in page_texts.items()
    }
    orphans = find_orphan_slugs(page_bodies)

    # --- Report ---
    has_issues = contradicted or orphans
    if not has_issues:
        # Still sync frontmatter to clear stale orphan: true flags from previous runs.
        _sync_orphan_frontmatter(wiki_dir, page_texts, set())
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

    # Sync orphan: true/false frontmatter so the Obsidian dashboard Dataview
    # query (WHERE orphan = true) reflects the same result as this report.
    _sync_orphan_frontmatter(wiki_dir, page_texts, set(orphans))

    typer.echo(
        f"\n{len(contradicted)} contradiction(s), {len(orphans)} orphan(s) found."
        f"\nDashboard: open wiki/dashboard.md in Obsidian for a live view."
    )
