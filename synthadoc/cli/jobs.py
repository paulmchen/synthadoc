# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import typer


def _fmt_ts(ts: str | None) -> str:
    """Convert a UTC SQLite timestamp string to local time for display."""
    if not ts:
        return "—"
    try:
        # SQLite datetime('now') returns "YYYY-MM-DD HH:MM:SS" (UTC, no tz marker)
        dt_utc = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
        return dt_utc.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return ts

from synthadoc.cli.main import app
from synthadoc.cli._http import get, post, delete as http_delete

jobs_app = typer.Typer(help="Manage background jobs.")
app.add_typer(jobs_app, name="jobs")


@jobs_app.command("list")
def jobs_list(
    status: Optional[str] = typer.Option(None, "--status", help="Filter by status"),
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
):
    """List all jobs for this wiki."""
    from synthadoc.cli._wiki import resolve_wiki
    wiki = resolve_wiki(wiki)
    params = {"status": status} if status else {}
    jobs = get(wiki, "/jobs", timeout=10, **params)
    if not jobs:
        typer.echo("No jobs found.")
        return
    for j in jobs:
        typer.echo(f"{j['id']}  {j['status']:<12}  {j['operation']:<8}  {_fmt_ts(j.get('created_at'))}")


@jobs_app.command("status")
def jobs_status(
    job_id: str = typer.Argument(..., help="Job ID returned by ingest/lint"),
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
):
    """Get the status of a specific job by ID."""
    from synthadoc.cli._wiki import resolve_wiki
    wiki = resolve_wiki(wiki)
    j = get(wiki, f"/jobs/{job_id}")
    typer.echo(f"ID:        {j['id']}")
    typer.echo(f"Status:    {j['status']}")
    typer.echo(f"Operation: {j['operation']}")
    typer.echo(f"Created:   {_fmt_ts(j.get('created_at'))}")
    if j.get("error"):
        typer.echo(f"Error:     {j['error']}")
    r = j.get("result") or {}
    if r.get("pages_created"):
        typer.echo(f"Created:   {', '.join(r['pages_created'])}")
    if r.get("pages_updated"):
        typer.echo(f"Updated:   {', '.join(r['pages_updated'])}")
    if r.get("pages_flagged"):
        typer.echo(f"Flagged:   {', '.join(r['pages_flagged'])}")
    if r.get("tokens_used"):
        typer.echo(f"Tokens:    {r['tokens_used']}")


@jobs_app.command("retry")
def jobs_retry(
    job_id: str = typer.Argument(...),
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
):
    """Reset a job to pending and re-queue it. Works for failed, dead, or stuck in-progress jobs."""
    from synthadoc.cli._wiki import resolve_wiki
    wiki = resolve_wiki(wiki)
    import asyncio
    from synthadoc.core.orchestrator import Orchestrator
    from synthadoc.cli.install import resolve_wiki_path

    async def run():
        orch = Orchestrator(wiki_root=resolve_wiki_path(wiki))
        await orch.init()
        await orch.queue.retry(job_id)
        typer.echo(f"Job {job_id} reset to pending.")

    asyncio.run(run())


@jobs_app.command("delete")
def jobs_delete(
    job_id: str = typer.Argument(...),
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
):
    """Delete a job."""
    from synthadoc.cli._wiki import resolve_wiki
    wiki = resolve_wiki(wiki)
    http_delete(wiki, f"/jobs/{job_id}")
    typer.echo(f"Deleted: {job_id}")


@jobs_app.command("cancel")
def jobs_cancel(
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Cancel all pending jobs (marks them as skipped)."""
    from synthadoc.cli._wiki import resolve_wiki
    wiki = resolve_wiki(wiki)
    from synthadoc.cli._http import post as http_post
    if not yes:
        typer.confirm("Cancel all pending jobs?", abort=True)
    r = http_post(wiki, "/jobs/cancel-pending", {})
    typer.echo(f"Cancelled {r['cancelled']} pending job(s).")


@jobs_app.command("purge")
def jobs_purge(
    older_than: int = typer.Option(30, "--older-than"),
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
):
    """Purge old completed/dead jobs."""
    from synthadoc.cli._wiki import resolve_wiki
    wiki = resolve_wiki(wiki)
    import asyncio
    from synthadoc.core.orchestrator import Orchestrator
    from synthadoc.cli.install import resolve_wiki_path

    async def run():
        orch = Orchestrator(wiki_root=resolve_wiki_path(wiki))
        await orch.init()
        count = await orch.queue.purge(older_than_days=older_than)
        typer.echo(f"Purged {count} jobs.")

    asyncio.run(run())
