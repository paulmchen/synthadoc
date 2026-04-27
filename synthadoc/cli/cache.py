# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from synthadoc.cli.main import app
from synthadoc.cli.install import resolve_wiki_path


@app.command("cache")
def cache_cmd(
    action: str = typer.Argument(..., help="Action to perform. Currently: 'clear'"),
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w",
                                        help="Path to wiki root (defaults to current directory)"),
):
    """Manage the LLM response cache."""
    from synthadoc.cli._wiki import resolve_wiki
    wiki = resolve_wiki(wiki)

    if action != "clear":
        typer.echo(f"Unknown action '{action}'. Available: clear", err=True)
        raise typer.Exit(1)

    import asyncio
    from synthadoc.core.cache import CacheManager

    root = resolve_wiki_path(wiki)
    db_path = root / ".synthadoc" / "cache.db"

    if not db_path.exists():
        typer.echo("No cache found — nothing to clear.")
        return

    async def _clear() -> int:
        cm = CacheManager(db_path)
        await cm.init()
        return await cm.clear()

    count = asyncio.run(_clear())
    typer.echo(f"Cache cleared: {count} entr{'y' if count == 1 else 'ies'} removed.")
