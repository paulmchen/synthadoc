# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from synthadoc.cli.main import app
from synthadoc.cli._http import get, post

_SUPPORTED = {".md", ".txt", ".pdf", ".docx", ".pptx", ".xlsx", ".csv",
              ".png", ".jpg", ".jpeg", ".webp", ".gif", ".tiff"}

# Intent-phrase prefixes that are valid non-file sources (matched case-insensitively)
_INTENT_PREFIXES = (
    "search for:", "find on the web:", "look up:", "web search:", "browse:",
    "fetch url:", "web page:", "website:",
)


def _validate_source(source: str) -> None:
    """Fail early if source is not a URL, an intent phrase, or an existing file path."""
    from synthadoc import errors as E
    s = source.strip()
    if s.startswith(("http://", "https://")):
        return  # URL — valid
    lower = s.lower()
    if any(lower.startswith(p) for p in _INTENT_PREFIXES):
        return  # Intent phrase — valid
    p = Path(s)
    if not (p if p.is_absolute() else p.resolve()).exists():
        E.cli_error(
            E.INGEST_NOT_FOUND,
            f"Source not found: '{s}'",
            "Provide a valid file path, a URL (https://…), or an intent phrase "
            "(e.g. 'search for: Bank of Canada rate outlook 2025').",
        )


@app.command("ingest")
def ingest_cmd(
    source: Optional[str] = typer.Argument(None, help="File or URL to ingest"),
    batch: bool = typer.Option(False, "--batch/--no-batch", help="Ingest directory"),
    file: Optional[str] = typer.Option(None, "--file", help="Manifest file of paths"),
    force: bool = typer.Option(False, "--force", help="Bypass dedup"),
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
    analyse_only: bool = typer.Option(False, "--analyse-only",
        help="Run analysis pass only; print result without writing wiki pages."),
    max_results: Optional[int] = typer.Option(None, "--max-results", "-n",
        help="Max URLs to ingest from a web search (overrides config default of 20)."),
):
    """Enqueue a source for ingestion. Requires synthadoc serve to be running."""
    from synthadoc.cli._wiki import resolve_wiki
    wiki = resolve_wiki(wiki)
    sources = []
    if batch and source:
        from synthadoc import errors as E
        p = Path(source)
        if not p.exists():
            E.cli_error(E.INGEST_NOT_FOUND, f"Directory not found: {p.resolve()}")
        if not p.is_dir():
            E.cli_error(E.INGEST_NOT_DIR,
                        f"{p.resolve()} is not a directory.",
                        "Use --batch with a folder path.")
        sources = [str(f) for f in p.rglob("*") if f.is_file() and f.suffix in _SUPPORTED]
        if not sources:
            typer.echo(
                f"No supported files found in {p.resolve()}\n"
                f"Supported formats: {', '.join(sorted(_SUPPORTED))}",
                err=True,
            )
            raise typer.Exit(1)
    elif file:
        sources = Path(file).read_text().splitlines()
    elif source:
        _validate_source(source)
        sources = [source]
    else:
        typer.echo("Provide a source file, --batch <dir>, or --file <manifest>.", err=True)
        raise typer.Exit(1)

    for s in sources:
        s = s.strip()
        if not s or s.startswith("#"):
            continue
        lower_s = s.lower()
        if s.startswith(("http://", "https://")) or any(lower_s.startswith(p) for p in _INTENT_PREFIXES):
            abs_source = s  # URLs and intent phrases are passed as-is to the server
        else:
            abs_source = str(Path(s).resolve())
        if analyse_only:
            import json as _json
            result = post(wiki, "/analyse", {"source": abs_source})
            typer.echo(_json.dumps(result, indent=2))
            continue
        body: dict = {"source": abs_source, "force": force}
        if max_results is not None:
            body["max_results"] = max_results
        result = post(wiki, "/jobs/ingest", body)
        typer.echo(f"Enqueued {s} → job {result['job_id']}")
        typer.echo(f"Check status: synthadoc jobs status {result['job_id']} -w {wiki}")
