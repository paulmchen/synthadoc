# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from synthadoc import __version__

app = typer.Typer(name="synthadoc", help="LLM knowledge compilation engine.",
                  add_completion=False)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context,
         version: bool = typer.Option(False, "--version", "-v"),
         wiki: Optional[str] = typer.Option(None, "--wiki", "-w")):
    if version:
        typer.echo(f"synthadoc {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


# Register sub-command modules
from synthadoc.cli import install  # noqa: F401, E402  (provides install + uninstall)
from synthadoc.cli import ingest, query, lint, status, jobs, serve  # noqa: F401, E402
from synthadoc.cli import demo  # noqa: F401, E402
from synthadoc.cli import schedule  # noqa: F401, E402
from synthadoc.cli import cache  # noqa: F401, E402
from synthadoc.cli import scaffold  # noqa: F401, E402
from synthadoc.cli.audit import audit_app  # noqa: F401, E402
app.add_typer(audit_app)
