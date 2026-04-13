# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import typer

from synthadoc.cli.main import app
from synthadoc.cli.install import resolve_wiki_path
from synthadoc import errors as E

_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:\|[^\]]*)?\]\]")


def _protected_slugs(wiki_dir: Path) -> list[str]:
    """Return slugs linked from index.md that have a corresponding wiki page."""
    index_path = wiki_dir / "wiki" / "index.md"
    if not index_path.exists():
        return []
    text = index_path.read_text(encoding="utf-8")
    slugs = []
    for m in _WIKILINK_RE.finditer(text):
        slug = m.group(1).strip()
        if (wiki_dir / "wiki" / f"{slug}.md").exists():
            slugs.append(slug)
    return slugs


def _run_scaffold(dest: Path, domain: str, protected_slugs: Optional[list[str]] = None):
    """Run ScaffoldAgent. Returns ScaffoldResult or None if no API key is set."""
    import asyncio
    import os
    from synthadoc.config import load_config
    from synthadoc.providers import make_provider

    cfg = load_config(project_config=dest / ".synthadoc" / "config.toml")
    provider_name = cfg.agents.resolve("ingest").provider

    _KEY_ENV = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "groq": "GROQ_API_KEY",
    }
    env_var = _KEY_ENV.get(provider_name)
    if env_var and not os.environ.get(env_var, "").strip():
        return None

    try:
        provider = make_provider("ingest", cfg)
        from synthadoc.agents.scaffold_agent import ScaffoldAgent
        agent = ScaffoldAgent(provider=provider)
        return asyncio.run(agent.scaffold(domain=domain, protected_slugs=protected_slugs))
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Scaffold LLM call failed: %s", exc)
        typer.echo(f"Error: LLM scaffold failed — {exc}", err=True)
        return None


@app.command("scaffold")
def scaffold_cmd(
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w", help="Wiki name or path"),
):
    """Re-generate domain-specific scaffold files for an existing wiki.

    Rewrites index.md, AGENTS.md, and purpose.md using the LLM.
    Pages linked from index.md that have existing wiki files are
    preserved as protected slugs. config.toml is never modified.

    Examples:

      synthadoc scaffold -w my-research

      synthadoc scaffold -w ~/wikis/my-research
    """
    if wiki is None:
        E.cli_error(
            E.WIKI_NOT_FOUND,
            "--wiki / -w is required.",
            "Provide a registered wiki name or a path: synthadoc scaffold -w <name-or-path>",
        )

    dest = resolve_wiki_path(wiki)

    if not dest.exists():
        E.cli_error(
            E.WIKI_NOT_FOUND,
            f"Wiki directory not found: {dest}",
            "Check the wiki name or path.",
        )

    cfg_path = dest / ".synthadoc" / "config.toml"
    if not cfg_path.exists():
        E.cli_error(
            E.CFG_NOT_FOUND,
            f"No config found at {cfg_path}",
            "Is this a valid synthadoc wiki directory?",
        )

    from synthadoc.config import load_config
    cfg = load_config(project_config=cfg_path)
    domain = cfg.wiki.domain

    slugs = _protected_slugs(dest)
    if slugs:
        typer.echo(f"Preserving {len(slugs)} protected page(s): {', '.join(slugs)}")

    typer.echo(f"Generating scaffold for domain: {domain}...")
    result = _run_scaffold(dest, domain, protected_slugs=slugs if slugs else None)

    if result is None:
        E.cli_error(
            E.CFG_MISSING_API_KEY,
            "Scaffold failed: no LLM API key found.",
            "Set your API key (e.g. ANTHROPIC_API_KEY) and try again.",
        )

    (dest / "wiki" / "index.md").write_text(result.index_md, encoding="utf-8", newline="\n")
    (dest / "AGENTS.md").write_text(result.agents_md, encoding="utf-8", newline="\n")
    (dest / "wiki" / "purpose.md").write_text(result.purpose_md, encoding="utf-8", newline="\n")

    typer.echo("Scaffold complete.")
    typer.echo(f"  index.md    updated")
    typer.echo(f"  AGENTS.md   updated")
    typer.echo(f"  purpose.md  updated")
