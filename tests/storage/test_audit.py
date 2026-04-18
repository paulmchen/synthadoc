# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
from synthadoc.storage.log import AuditDB, LogWriter


@pytest.mark.asyncio
async def test_record_query_stored_and_retrievable(tmp_wiki):
    """record_query() must persist a query event retrievable via list_queries()."""
    db = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await db.init()
    await db.record_query(
        question="What is Moore's Law?",
        sub_questions_count=1,
        tokens=125,
        cost_usd=0.0004,
    )
    records = await db.list_queries(limit=10)
    assert len(records) == 1
    assert records[0]["question"] == "What is Moore's Law?"
    assert records[0]["sub_questions_count"] == 1
    assert records[0]["tokens"] == 125


@pytest.mark.asyncio
async def test_cost_summary_includes_query_costs(tmp_wiki):
    """cost_summary() must aggregate both ingest and query token costs."""
    db = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await db.init()
    await db.record_ingest(
        source_hash="abc", source_size=100, source_path="test.md",
        wiki_page="test", tokens=500, cost_usd=0.002,
    )
    await db.record_query(
        question="test question", sub_questions_count=2,
        tokens=200, cost_usd=0.0008,
    )
    summary = await db.cost_summary(days=30)
    assert summary["total_tokens"] == 700
    assert abs(summary["total_cost_usd"] - 0.0028) < 0.0001


def test_log_writer_logs_query(tmp_wiki):
    """log_query() must append a QUERY entry to the activity log."""
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    log.log_query(question="What is Moore's Law?", sub_questions=2,
                  citations=["moores-law"], tokens=125, cost_usd=0.0004)
    content = (tmp_wiki / "wiki" / "log.md").read_text(encoding="utf-8")
    assert "QUERY" in content
    assert "Moore" in content
    assert "125" in content


def test_log_writer_logs_query_with_no_citations(tmp_wiki):
    """log_query() with empty citations must write 'none', not crash."""
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    log.log_query(question="unknown topic?", sub_questions=1,
                  citations=[], tokens=80, cost_usd=0.0002)
    content = (tmp_wiki / "wiki" / "log.md").read_text(encoding="utf-8")
    assert "QUERY" in content
    assert "none" in content


@pytest.mark.asyncio
async def test_list_queries_returns_most_recent_first(tmp_wiki):
    """list_queries() must return records in reverse-insertion order (most recent first)."""
    db = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await db.init()
    await db.record_query(question="first question", sub_questions_count=1, tokens=100, cost_usd=0.0003)
    await db.record_query(question="second question", sub_questions_count=2, tokens=150, cost_usd=0.0005)
    records = await db.list_queries(limit=10)
    assert records[0]["question"] == "second question"
    assert records[1]["question"] == "first question"


@pytest.mark.asyncio
async def test_list_queries_respects_limit(tmp_wiki):
    """list_queries(limit=N) must return at most N records."""
    db = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await db.init()
    for i in range(5):
        await db.record_query(question=f"question {i}", sub_questions_count=1,
                               tokens=50, cost_usd=0.0001)
    records = await db.list_queries(limit=3)
    assert len(records) == 3
