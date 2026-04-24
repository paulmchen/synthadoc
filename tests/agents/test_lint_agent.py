# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest
from unittest.mock import AsyncMock
from synthadoc.agents.lint_agent import LintAgent, LintReport, find_orphan_slugs, LINT_SKIP_SLUGS
from synthadoc.providers.base import CompletionResponse
from synthadoc.storage.wiki import WikiStorage, WikiPage
from synthadoc.storage.log import LogWriter


@pytest.mark.asyncio
async def test_lint_finds_contradictions(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("p1", WikiPage(title="P1", tags=[], content="⚠ conflict",
        status="contradicted", confidence="low", sources=[]))
    store.write_page("p2", WikiPage(title="P2", tags=[], content="Normal.",
        status="active", confidence="high", sources=[]))
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text="Resolution.", input_tokens=50, output_tokens=10)
    agent = LintAgent(provider=provider, store=store, log_writer=log)
    report = await agent.lint(scope="contradictions")
    assert report.contradictions_found == 1


@pytest.mark.asyncio
async def test_lint_finds_orphans(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("hub", WikiPage(title="Hub", tags=[], content="See [[linked]].",
        status="active", confidence="medium", sources=[]))
    store.write_page("linked", WikiPage(title="Linked", tags=[], content="content",
        status="active", confidence="medium", sources=[]))
    store.write_page("orphan", WikiPage(title="Orphan", tags=[], content="alone",
        status="active", confidence="medium", sources=[]))
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    agent = LintAgent(provider=AsyncMock(), store=store, log_writer=log)
    report = await agent.lint(scope="orphans")
    assert "orphan" in report.orphan_slugs
    assert "index" not in report.orphan_slugs
    assert "dashboard" not in report.orphan_slugs
    assert "log" not in report.orphan_slugs


@pytest.mark.asyncio
async def test_lint_aliased_wikilink_not_orphan(tmp_wiki):
    """[[slug|Display Text]] aliases should not cause the target to be flagged as orphan."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("hub", WikiPage(title="Hub", tags=[],
        content="See [[quantum-computing|Quantum Computing]] for details.",
        status="active", confidence="medium", sources=[]))
    store.write_page("quantum-computing", WikiPage(title="Quantum Computing", tags=[],
        content="content", status="active", confidence="medium", sources=[]))
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    agent = LintAgent(provider=AsyncMock(), store=store, log_writer=log)
    report = await agent.lint(scope="orphans")
    assert "quantum-computing" not in report.orphan_slugs


def test_find_orphan_slugs_basic():
    """Pages with no inbound links from content pages are orphans."""
    page_texts = {
        "page-a": "See [[page-b]].",
        "page-b": "No links here.",
        "page-c": "Standalone page.",
    }
    orphans = find_orphan_slugs(page_texts)
    assert "page-a" in orphans      # nothing links to page-a
    assert "page-b" not in orphans  # page-a links to page-b
    assert "page-c" in orphans      # nothing links to page-c


def test_find_orphan_slugs_overview_excluded():
    """Links from overview (and other skip slugs) must not count as real references."""
    page_texts = {
        "overview": "[[page-a]] [[page-b]]",
        "page-a":   "See [[page-b]].",
        "page-b":   "No links here.",
    }
    orphans = find_orphan_slugs(page_texts)
    assert "overview" not in orphans   # skip slugs never reported
    assert "page-a" in orphans         # overview link doesn't count; nothing else links to page-a
    assert "page-b" not in orphans     # page-a links to page-b → not an orphan


def test_find_orphan_slugs_skip_slugs_never_reported():
    """Skip slugs (index, dashboard, …) are never returned as orphans."""
    page_texts = {slug: "" for slug in LINT_SKIP_SLUGS}
    page_texts["real-page"] = "content"
    orphans = find_orphan_slugs(page_texts)
    for slug in LINT_SKIP_SLUGS:
        assert slug not in orphans


def test_find_orphan_slugs_self_link_does_not_prevent_orphan():
    """A page that links only to itself must still be reported as an orphan."""
    page_texts = {
        "lonely": "See also [[lonely]] for more.",  # self-link
        "hub":    "Links to [[real-page]].",
        "real-page": "No outbound links.",
    }
    orphans = find_orphan_slugs(page_texts)
    assert "lonely" in orphans       # self-link must not count as an inbound reference
    assert "real-page" not in orphans  # hub links to real-page → not an orphan
    assert "hub" in orphans            # nothing links to hub


@pytest.mark.asyncio
async def test_lint_skip_slugs_not_counted_as_contradictions(tmp_wiki):
    """index, dashboard, and other auto-generated pages must never appear in contradiction reports."""
    store = WikiStorage(tmp_wiki / "wiki")
    for slug in LINT_SKIP_SLUGS:
        store.write_page(slug, WikiPage(title=slug.title(), tags=[],
            content="auto-generated", status="contradicted",
            confidence="low", sources=[]))
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    agent = LintAgent(provider=AsyncMock(), store=store, log_writer=log)
    report = await agent.lint(scope="contradictions")
    assert report.contradictions_found == 0
