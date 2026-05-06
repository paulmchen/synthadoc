# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import typer

from synthadoc.cli.main import app

context_app = typer.Typer(name="context", help="Build token-bounded evidence packs from the wiki.")
app.add_typer(context_app)


def _build_context_pack(wiki_or_root: str, goal: str, tokens: int) -> str:
    """Call server POST /context/build and return Markdown string."""
    from synthadoc.cli._http import post
    result = post(wiki_or_root, "/context/build", {"goal": goal, "token_budget": tokens})
    from synthadoc.agents.context_agent import ContextPack, ContextPage
    pages = [
        ContextPage(
            slug=p["slug"], relevance=p.get("relevance", 0.0),
            excerpt=p.get("excerpt", ""), source=p.get("source", ""),
            confidence=p.get("confidence", "medium"),
            tags=p.get("tags", []),
            estimated_tokens=p.get("estimated_tokens", 0),
        )
        for p in result.get("pages", [])
    ]
    omitted = [
        ContextPage(
            slug=o["slug"], relevance=0.0, excerpt="", source="",
            confidence="", tags=[],
            estimated_tokens=o.get("estimated_tokens", 0),
        )
        for o in result.get("omitted", [])
    ]
    pack = ContextPack(
        goal=result.get("goal", goal),
        token_budget=result.get("token_budget", tokens),
        tokens_used=result.get("tokens_used", 0),
        pages=pages,
        omitted=omitted,
    )
    return pack.to_markdown()


@context_app.command("build")
def context_build(
    goal: str = typer.Argument(..., help="Goal or topic to build context for"),
    tokens: int = typer.Option(4000, "--tokens", help="Token budget"),
    output: Optional[str] = typer.Option(None, "--output", help="Save to file"),
    save: bool = typer.Option(False, "--save", help="Save to wiki/context/"),
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
    wiki_root: Optional[str] = typer.Option(None, "--wiki-root"),
) -> None:
    """Build a token-bounded, cited evidence pack from the wiki."""
    from synthadoc.cli._wiki import resolve_wiki
    wiki_name = wiki or resolve_wiki(None)
    wiki_root_path = Path(wiki_root) if wiki_root else None

    markdown = _build_context_pack(wiki_root_path or wiki_name, goal, tokens)

    if output:
        Path(output).write_text(markdown, encoding="utf-8")
        typer.echo(f"Context pack saved to {output}")
    elif save and wiki_root_path:
        slug = re.sub(r"[^\w]+", "-", goal.lower()).strip("-")[:50]
        dest = wiki_root_path / "wiki" / "context" / f"{slug}.md"
        dest.parent.mkdir(exist_ok=True)
        dest.write_text(markdown, encoding="utf-8")
        typer.echo(f"Context pack saved to {dest}")
    else:
        typer.echo(markdown)
