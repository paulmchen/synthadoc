# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest
import json
from synthadoc.storage.log import AuditDB


@pytest.fixture
async def populated_audit_db(tmp_path):
    db = AuditDB(tmp_path / "audit.db")
    await db.init()
    for i in range(3):
        await db.record_ingest(
            source_hash=f"hash{i}", source_size=1000 + i,
            source_path=f"/wiki/raw/doc{i}.pdf", wiki_page=f"page-{i}",
            tokens=500 + i * 100, cost_usd=0.01 * (i + 1),
        )
    await db.record_audit_event("job-1", "ingest_complete", {"pages": 1})
    await db.record_audit_event("job-2", "lint_complete", {"resolved": 0})
    return db


@pytest.mark.asyncio
async def test_list_ingests_returns_records(populated_audit_db):
    records = await populated_audit_db.list_ingests(limit=10)
    assert len(records) == 3
    assert records[0]["source_path"] == "/wiki/raw/doc0.pdf"
    assert "tokens" in records[0]
    assert "cost_usd" in records[0]
    assert "ingested_at" in records[0]


@pytest.mark.asyncio
async def test_list_ingests_respects_limit(populated_audit_db):
    records = await populated_audit_db.list_ingests(limit=2)
    assert len(records) == 2


@pytest.mark.asyncio
async def test_list_events_returns_records(populated_audit_db):
    events = await populated_audit_db.list_events(limit=10)
    assert len(events) == 2
    assert events[0]["event"] in ("ingest_complete", "lint_complete")


@pytest.mark.asyncio
async def test_cost_summary_aggregates_correctly(populated_audit_db):
    summary = await populated_audit_db.cost_summary(days=30)
    assert summary["total_tokens"] == 500 + 600 + 700
    assert abs(summary["total_cost_usd"] - 0.06) < 0.001
    assert "daily" in summary


def test_audit_history_command_prints_table(tmp_path):
    from typer.testing import CliRunner
    from synthadoc.cli.main import app

    runner = CliRunner()
    wiki = tmp_path
    (wiki / "wiki").mkdir()
    (wiki / ".synthadoc").mkdir()

    result = runner.invoke(app, ["audit", "history", "--wiki", str(wiki)])
    assert result.exit_code == 0


def test_audit_history_json_flag(tmp_path):
    from typer.testing import CliRunner
    from synthadoc.cli.main import app

    runner = CliRunner()
    wiki = tmp_path
    (wiki / "wiki").mkdir()
    (wiki / ".synthadoc").mkdir()

    result = runner.invoke(app, ["audit", "history", "--wiki", str(wiki), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)


def test_audit_cost_command(tmp_path):
    from typer.testing import CliRunner
    from synthadoc.cli.main import app

    runner = CliRunner()
    wiki = tmp_path
    (wiki / "wiki").mkdir()
    (wiki / ".synthadoc").mkdir()

    result = runner.invoke(app, ["audit", "cost", "--wiki", str(wiki)])
    assert result.exit_code == 0


def test_audit_events_command(tmp_path):
    from typer.testing import CliRunner
    from synthadoc.cli.main import app

    runner = CliRunner()
    wiki = tmp_path
    (wiki / "wiki").mkdir()
    (wiki / ".synthadoc").mkdir()

    result = runner.invoke(app, ["audit", "events", "--wiki", str(wiki)])
    assert result.exit_code == 0
