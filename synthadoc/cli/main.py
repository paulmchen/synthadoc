# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import typer

from synthadoc import __version__
from synthadoc.cli._wiki import (
    ENV_VAR as _WIKI_ENV_VAR,
    _normalise_wiki_name,
    _read_default_wiki,
    _write_default_wiki,
)

app = typer.Typer(name="synthadoc", help="LLM knowledge compilation engine.",
                  add_completion=False)


def _resolve_wiki_path(wiki: str) -> Path:
    """Thin wrapper around install.resolve_wiki_path — lazy to avoid circular import."""
    from synthadoc.cli.install import resolve_wiki_path
    return resolve_wiki_path(wiki)


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


@app.command("use")
def use_cmd(
    wiki: Optional[str] = typer.Argument(None, help="Wiki name to set as default"),
    clear: bool = typer.Option(False, "--clear", help="Clear the saved default wiki"),
):
    """Set or show the default wiki — eliminates -w on every command.

    \b
    Examples:
      synthadoc use my-wiki          # save as default for all commands
      synthadoc use                  # show which wiki is currently active
      synthadoc use --clear          # clear the saved default
      synthadoc use -w other-wiki    # one-off: see status of a different wiki
    """
    if clear:
        _write_default_wiki(None)
        typer.echo("Saved default wiki cleared.")
        return

    if wiki is None:
        env_wiki = os.environ.get(_WIKI_ENV_VAR, "").strip() or None
        saved_wiki = _read_default_wiki()
        if env_wiki:
            typer.echo(
                f"Active wiki: '{env_wiki}'\n"
                f"  Source: {_WIKI_ENV_VAR} environment variable\n"
                f"  To switch: export {_WIKI_ENV_VAR}=<other-name>"
            )
        elif saved_wiki:
            typer.echo(
                f"Active wiki: '{saved_wiki}'\n"
                f"  Source: saved default (~/.synthadoc/default_wiki)\n"
                f"  To switch: synthadoc use <other-name>\n"
                f"  To clear:  synthadoc use --clear"
            )
        else:
            typer.echo(
                f"No default wiki set.\n"
                f"  Run 'synthadoc use <name>' to save one, or:\n"
                f"  Set {_WIKI_ENV_VAR}=<name> in your shell profile for session scope."
            )
        return

    wiki = _normalise_wiki_name(wiki)
    # Validate the wiki exists
    path = _resolve_wiki_path(wiki)
    if not (path / ".synthadoc" / "config.toml").exists():
        typer.echo(
            f"Warning: '{wiki}' is not a registered wiki (not found at '{path}').\n"
            "  Run 'synthadoc list' to see registered wikis. Saving anyway.",
            err=True,
        )
    _write_default_wiki(wiki)
    typer.echo(
        f"Default wiki set to '{wiki}'.\n"
        f"  All subsequent commands use this wiki unless you pass -w <name>.\n"
        f"  To switch:   synthadoc use <other-name>\n"
        f"  To override: synthadoc <cmd> -w <other-name>\n"
        f"  To clear:    synthadoc use --clear"
    )


# Register sub-command modules
from synthadoc.cli import install  # noqa: F401, E402  (provides install + uninstall)
from synthadoc.cli import ingest, query, lint, status, jobs, serve  # noqa: F401, E402
from synthadoc.cli import demo  # noqa: F401, E402
from synthadoc.cli import schedule  # noqa: F401, E402
from synthadoc.cli import cache  # noqa: F401, E402
from synthadoc.cli import scaffold  # noqa: F401, E402
from synthadoc.cli.audit import audit_app  # noqa: F401, E402
app.add_typer(audit_app)
from synthadoc.cli.routing import routing_app  # noqa: F401, E402
app.add_typer(routing_app)
