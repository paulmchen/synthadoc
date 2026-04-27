# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from synthadoc.cli.main import app
from synthadoc.cli.install import resolve_wiki_path
from synthadoc import errors as E

schedule_app = typer.Typer(help="Manage recurring scheduled operations.")
app.add_typer(schedule_app, name="schedule")


def _resolve_and_validate(wiki: Optional[str]) -> Path:
    """Resolve wiki name to path and fail early if it is not installed."""
    if wiki is None:
        E.cli_error(
            E.WIKI_NOT_FOUND,
            "--wiki / -w is required for schedule commands.",
            "Provide a registered wiki name: synthadoc schedule <cmd> -w <name>",
        )
    root = resolve_wiki_path(wiki)
    if not (root / ".synthadoc" / "config.toml").exists():
        E.cli_error(
            E.WIKI_NOT_REGISTERED,
            f"Wiki '{wiki}' is not installed.",
            f"Make sure wiki '{wiki}' was installed with 'synthadoc install'.",
        )
    return root


@schedule_app.command("add")
def add_cmd(
    op: str = typer.Option(..., "--op", help="synthadoc operation (e.g. 'lint')"),
    cron: str = typer.Option(..., "--cron", help="Cron expression"),
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
):
    """Register a recurring operation with the OS scheduler."""
    from synthadoc.cli._wiki import resolve_wiki
    wiki = resolve_wiki(wiki)
    from synthadoc.core.scheduler import Scheduler
    root = _resolve_and_validate(wiki)
    sched = Scheduler(wiki=wiki, wiki_root=str(root))
    entry_id = sched.add(op=op, cron=cron)
    typer.echo(f"Scheduled: {entry_id}")


@schedule_app.command("list")
def list_cmd(wiki: Optional[str] = typer.Option(None, "--wiki", "-w")):
    """List all synthadoc-registered scheduled jobs."""
    from synthadoc.cli._wiki import resolve_wiki
    wiki = resolve_wiki(wiki)
    from synthadoc.core.scheduler import Scheduler
    root = _resolve_and_validate(wiki)
    sched = Scheduler(wiki=wiki, wiki_root=str(root))
    for e in sched.list():
        typer.echo(f"{e.id}  {e.cron}  {e.op}")


@schedule_app.command("remove")
def remove_cmd(
    entry_id: str = typer.Argument(...),
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
):
    """Remove a scheduled job by ID."""
    from synthadoc.cli._wiki import resolve_wiki
    wiki = resolve_wiki(wiki)
    from synthadoc.core.scheduler import Scheduler
    root = _resolve_and_validate(wiki)
    sched = Scheduler(wiki=wiki, wiki_root=str(root))
    sched.remove(entry_id)
    typer.echo(f"Removed: {entry_id}")


@schedule_app.command("apply")
def apply_cmd(wiki: Optional[str] = typer.Option(None, "--wiki", "-w")):
    """Register all jobs declared in [schedule] in the project config."""
    from synthadoc.cli._wiki import resolve_wiki
    wiki = resolve_wiki(wiki)
    from synthadoc.config import load_config
    from synthadoc.core.scheduler import Scheduler, ScheduleEntry
    root = _resolve_and_validate(wiki)
    cfg = load_config(project_config=root / ".synthadoc" / "config.toml")
    sched = Scheduler(wiki=wiki, wiki_root=str(root))
    ids = sched.apply([ScheduleEntry(op=j.op, cron=j.cron, wiki=wiki)
                       for j in cfg.schedule.jobs])
    for entry_id in ids:
        typer.echo(f"Registered: {entry_id}")
