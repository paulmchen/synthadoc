# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from synthadoc.cli.main import app
from synthadoc.cli._http import get, post

_SUPPORTED = {".md", ".txt", ".pdf", ".docx", ".xlsx", ".csv",
              ".png", ".jpg", ".jpeg", ".webp", ".gif", ".tiff"}


@app.command("ingest")
def ingest_cmd(
    source: Optional[str] = typer.Argument(None, help="File or URL to ingest"),
    batch: bool = typer.Option(False, "--batch/--no-batch", help="Ingest directory"),
    file: Optional[str] = typer.Option(None, "--file", help="Manifest file of paths"),
    force: bool = typer.Option(False, "--force", help="Bypass dedup"),
    wiki: str = typer.Option(".", "--wiki", "-w"),
    analyse_only: bool = typer.Option(False, "--analyse-only",
        help="Run analysis pass only; print result without writing wiki pages."),
):
    """Enqueue a source for ingestion. Requires synthadoc serve to be running."""
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
        sources = [source]
    else:
        typer.echo("Provide a source file, --batch <dir>, or --file <manifest>.", err=True)
        raise typer.Exit(1)

    for s in sources:
        s = s.strip()
        if not s or s.startswith("#"):
            continue
        abs_source = s if s.startswith(("http://", "https://")) else str(Path(s).resolve())
        if analyse_only:
            import json as _json
            result = post(wiki, "/analyse", {"source": abs_source})
            typer.echo(_json.dumps(result, indent=2))
            continue
        result = post(wiki, "/jobs/ingest", {"source": abs_source, "force": force})
        typer.echo(f"Enqueued {s} → job {result['job_id']}")
        typer.echo(f"Check status: synthadoc jobs status {result['job_id']} -w {wiki}")
