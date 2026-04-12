# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from synthadoc.cli.install import resolve_wiki_path

audit_app = typer.Typer(name="audit", help="Inspect ingest history and costs.")
console = Console()


def _get_audit_db(wiki: Optional[str]):
    from synthadoc.storage.log import AuditDB
    root = resolve_wiki_path(wiki) if wiki else Path(".")
    return AuditDB(root / ".synthadoc" / "audit.db")


@audit_app.command("history")
def history_cmd(
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
    limit: int = typer.Option(50, "--limit", "-n"),
    as_json: bool = typer.Option(False, "--json", help="Output raw JSON"),
):
    """Show recent ingest history."""
    db = _get_audit_db(wiki)

    async def _fetch():
        await db.init()
        return await db.list_ingests(limit=limit)

    records = asyncio.run(_fetch())
    if as_json:
        typer.echo(json.dumps(records, indent=2))
        return
    table = Table(title=f"Ingest History (last {limit})")
    table.add_column("Timestamp", style="dim")
    table.add_column("Source")
    table.add_column("Wiki Page", style="cyan")
    table.add_column("Tokens", justify="right")
    table.add_column("Cost (USD)", justify="right")
    for r in records:
        table.add_row(
            r.get("ingested_at", "")[:16],
            Path(r.get("source_path", "")).name,
            r.get("wiki_page", ""),
            str(r.get("tokens") or 0),
            f"${r.get('cost_usd') or 0:.4f}",
        )
    console.print(table)


@audit_app.command("cost")
def cost_cmd(
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
    days: int = typer.Option(30, "--days"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Show token and cost summary."""
    db = _get_audit_db(wiki)

    async def _fetch():
        await db.init()
        return await db.cost_summary(days=days)

    summary = asyncio.run(_fetch())
    if as_json:
        typer.echo(json.dumps(summary, indent=2))
        return
    console.print(f"\n[bold]Cost summary — last {days} days[/bold]")
    console.print(f"  Total tokens : {summary['total_tokens']:,}")
    console.print(f"  Total cost   : ${summary['total_cost_usd']:.4f}")
    if summary["daily"]:
        table = Table(title="Daily breakdown")
        table.add_column("Day")
        table.add_column("Cost (USD)", justify="right")
        for row in summary["daily"]:
            table.add_row(row["day"], f"${row['cost_usd']:.4f}")
        console.print(table)


@audit_app.command("events")
def events_cmd(
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
    limit: int = typer.Option(100, "--limit", "-n"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Show raw audit events."""
    db = _get_audit_db(wiki)

    async def _fetch():
        await db.init()
        return await db.list_events(limit=limit)

    events = asyncio.run(_fetch())
    if as_json:
        typer.echo(json.dumps(events, indent=2))
        return
    table = Table(title=f"Audit Events (last {limit})")
    table.add_column("Timestamp", style="dim")
    table.add_column("Job ID", style="dim")
    table.add_column("Event", style="cyan")
    table.add_column("Metadata")
    for e in events:
        table.add_row(
            e.get("timestamp", "")[:16],
            e.get("job_id") or "",
            e.get("event", ""),
            e.get("metadata") or "",
        )
    console.print(table)
