# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import typer

from synthadoc.cli.main import app
from synthadoc.cli._http import get


def _format_gap_callout(suggested_searches: list[str], wiki: str) -> str:
    """Build the Obsidian [!tip] callout for a knowledge gap."""
    terminal_cmds = "\n".join(
        f'synthadoc ingest "search for: {s}" -w {wiki}'
        for s in suggested_searches
    )
    return (
        "\n---\n\n"
        "> [!tip] Knowledge Gap Detected\n"
        "> Your wiki doesn't have enough on this topic yet. Enrich it with a web search:\n"
        ">\n"
        "> **From Obsidian:** Open Command Palette (`Cmd+P` / `Ctrl+P`) "
        "→ **Synthadoc: Ingest: web search**\n"
        ">\n"
        "> **From the terminal:**\n"
        "> ```bash\n"
        + "\n".join(f"> {cmd}" for cmd in terminal_cmds.splitlines()) + "\n"
        "> ```\n"
        ">\n"
        "> After ingesting, re-run your query to get a richer answer."
    )


@app.command("query")
def query_cmd(
    question: str = typer.Argument(..., help="Question to ask the wiki"),
    save: bool = typer.Option(False, "--save", help="Save answer as wiki page"),
    wiki: str = typer.Option(".", "--wiki", "-w"),
    timeout: int = typer.Option(60, "--timeout", help="Seconds to wait for the LLM (default 60; increase for slow providers)"),
):
    """Query the wiki. Requires synthadoc serve to be running."""
    result = get(wiki, "/query", timeout=timeout, q=question)
    typer.echo(result["answer"])
    if result.get("citations"):
        typer.echo("\nSources: " + ", ".join(f"[[{c}]]" for c in result["citations"]))
    if result.get("knowledge_gap") and result.get("suggested_searches"):
        typer.echo(_format_gap_callout(result["suggested_searches"], wiki))
