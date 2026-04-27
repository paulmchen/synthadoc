# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import typer

ENV_VAR = "SYNTHADOC_WIKI"
DEFAULT_WIKI_FILE = Path.home() / ".synthadoc" / "default_wiki"


def _read_default_wiki() -> Optional[str]:
    """Return the saved default wiki name, or None if not set."""
    try:
        text = DEFAULT_WIKI_FILE.read_text(encoding="utf-8").strip()
        return text or None
    except FileNotFoundError:
        return None


def _write_default_wiki(name: Optional[str]) -> None:
    """Write (or clear) the saved default wiki name."""
    DEFAULT_WIKI_FILE.parent.mkdir(parents=True, exist_ok=True)
    if name:
        DEFAULT_WIKI_FILE.write_text(name.strip(), encoding="utf-8")
    elif DEFAULT_WIKI_FILE.exists():
        DEFAULT_WIKI_FILE.unlink()


def resolve_wiki(explicit: Optional[str]) -> str:
    """Resolve the active wiki from the priority chain.

    Priority: explicit -w arg > SYNTHADOC_WIKI env var >
              ~/.synthadoc/default_wiki > CWD fallback > error.

    All hint messages are written to stderr so stdout stays
    machine-readable for automation pipelines.
    """
    env_wiki = os.environ.get(ENV_VAR, "").strip() or None
    saved_wiki = _read_default_wiki()

    if explicit is not None:
        if env_wiki and explicit != env_wiki:
            typer.echo(
                f"[wiki: {explicit}]  overrides {ENV_VAR}='{env_wiki}'",
                err=True,
            )
        elif saved_wiki and explicit != saved_wiki:
            typer.echo(
                f"[wiki: {explicit}]  overrides saved default '{saved_wiki}'",
                err=True,
            )
        else:
            typer.echo(f"[wiki: {explicit}]", err=True)
        return explicit

    if env_wiki:
        typer.echo(f"[wiki: {env_wiki}]", err=True)
        return env_wiki

    if saved_wiki:
        typer.echo(f"[wiki: {saved_wiki}]", err=True)
        return saved_wiki

    # Backward compat: user is inside a wiki directory
    if Path(".synthadoc/config.toml").exists():
        cwd_name = Path(".").resolve().name
        typer.echo(f"[wiki: {cwd_name} (current directory)]", err=True)
        return "."

    typer.echo(
        "Error: No wiki specified.\n"
        "  Pass -w <name> on this command, or run 'synthadoc use <name>' to\n"
        "  save a default — you won't need -w again unless switching wikis.",
        err=True,
    )
    raise typer.Exit(1)
