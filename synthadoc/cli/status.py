# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

from typing import Optional

import typer

from synthadoc.cli.main import app
from synthadoc.cli._http import get


@app.command("status")
def status_cmd(wiki: Optional[str] = typer.Option(None, "--wiki", "-w")):
    """Show wiki status. Requires synthadoc serve to be running."""
    from synthadoc.cli._wiki import resolve_wiki
    wiki = resolve_wiki(wiki)
    result = get(wiki, "/status")
    typer.echo(f"Wiki:         {result['wiki']}")
    typer.echo(f"Pages:        {result['pages']}")
    typer.echo(f"Jobs pending: {result['jobs_pending']}")
    typer.echo(f"Jobs total:   {result['jobs_total']}")
