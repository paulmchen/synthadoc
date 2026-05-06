# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest
from unittest.mock import AsyncMock
from synthadoc.agents.lint_agent import LintAgent, LintReport, find_orphan_slugs, LINT_SKIP_SLUGS, LINT_SKIP_SOURCE_SLUGS
from synthadoc.providers.base import CompletionResponse
from synthadoc.storage.wiki import WikiStorage, WikiPage
from synthadoc.storage.log import LogWriter, AuditDB


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


def test_find_orphan_slugs_index_links_do_not_rescue():
    """Links from index.md must NOT rescue pages from orphan status.
    index is a directory page; only content-page links count.
    index itself must never appear in the orphan report."""
    page_texts = {
        "index":   "## Recently Added\n- [[page-a]]\n",
        "page-a":  "No outbound links.",
        "page-b":  "No outbound links.",
    }
    orphans = find_orphan_slugs(page_texts)
    assert "page-a" in orphans       # index link doesn't count → still orphan
    assert "page-b" in orphans       # nothing links to page-b → orphan
    assert "index" not in orphans    # index itself never reported as orphan


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


@pytest.mark.asyncio
async def test_orphan_flag_cleared_when_inbound_link_added(tmp_wiki):
    """Page with orphan=True transitions to orphan=False once another page links to it."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("page-a", WikiPage(title="Page A", tags=[],
        content="Content of page A.", status="active", confidence="high",
        sources=[], orphan=True))
    store.write_page("page-b", WikiPage(title="Page B", tags=[],
        content="Links to [[page-a]] here.", status="active", confidence="high",
        sources=[]))

    assert store.read_page("page-a").orphan is True

    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    agent = LintAgent(provider=AsyncMock(), store=store, log_writer=log)
    await agent.lint(scope="orphans")

    assert store.read_page("page-a").orphan is False


# ── CJK (Chinese / Japanese / Korean) coverage ───────────────────────────────

def test_find_orphan_slugs_cjk_wikilinks():
    """[[量子计算]] wikilinks with CJK targets are parsed correctly by the orphan detector."""
    page_texts = {
        "人工智能":  "人工智能是一个广泛的领域，包括[[机器学习]]和[[量子计算]]。",
        "机器学习":  "机器学习是人工智能的子领域。",
        "量子计算":  "量子计算利用量子力学原理。",
        "深度学习":  "深度学习是机器学习的一种方法。没有人链接到这里。",
    }
    orphans = find_orphan_slugs(page_texts)

    assert "机器学习" not in orphans      # linked from 人工智能
    assert "量子计算" not in orphans      # linked from 人工智能
    assert "深度学习" in orphans          # no inbound links
    assert "人工智能" in orphans          # nothing links to 人工智能


@pytest.mark.asyncio
async def test_lint_cjk_orphan_detection(tmp_wiki):
    """Full async lint correctly identifies orphans among CJK-slugged pages."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("人工智能", WikiPage(title="人工智能", tags=[],
        content="参见[[机器学习]]了解更多。",
        status="active", confidence="medium", sources=[]))
    store.write_page("机器学习", WikiPage(title="机器学习", tags=[],
        content="机器学习是一种技术。",
        status="active", confidence="medium", sources=[]))
    store.write_page("量子计算", WikiPage(title="量子计算", tags=[],
        content="量子计算尚未在本维基中建立链接。",
        status="active", confidence="medium", sources=[]))

    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    agent = LintAgent(provider=AsyncMock(), store=store, log_writer=log)
    report = await agent.lint(scope="orphans")

    assert "量子计算" in report.orphan_slugs    # no inbound link
    assert "机器学习" not in report.orphan_slugs  # linked from 人工智能


@pytest.mark.asyncio
async def test_lint_cjk_contradiction_detected(tmp_wiki):
    """CJK page with contradicted status is found and included in the contradiction report."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("量子纠错", WikiPage(title="量子纠错", tags=[],
        content="⚠ 此页面存在矛盾内容。量子纠错需要大量量子比特。",
        status="contradicted", confidence="low", sources=[]))
    store.write_page("人工智能", WikiPage(title="人工智能", tags=[],
        content="正常内容，没有矛盾。",
        status="active", confidence="high", sources=[]))

    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text="矛盾已解决。", input_tokens=50, output_tokens=10)
    agent = LintAgent(provider=provider, store=store, log_writer=log)
    report = await agent.lint(scope="contradictions")

    assert report.contradictions_found == 1


@pytest.mark.asyncio
async def test_lint_records_contradiction_found_audit_event(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("p1", WikiPage(title="P1", tags=[], content="⚠ conflict",
        status="contradicted", confidence="low", sources=[]))
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AsyncMock(spec=AuditDB)
    agent = LintAgent(provider=AsyncMock(), store=store, log_writer=log, audit_db=audit)
    await agent.lint(scope="contradictions", job_id="job-123")
    audit.record_audit_event.assert_awaited_once_with("job-123", "contradiction_found", {"slug": "p1"})


@pytest.mark.asyncio
async def test_lint_records_auto_resolved_audit_event(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("p1", WikiPage(title="P1", tags=[], content="⚠ conflict",
        status="contradicted", confidence="low", sources=[]))
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AsyncMock(spec=AuditDB)
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text='{"resolvable": true, "reason": "Claims reconciled.", "resolution": "Reconciled content."}',
        input_tokens=10, output_tokens=5,
    )
    agent = LintAgent(provider=provider, store=store, log_writer=log, audit_db=audit)
    await agent.lint(scope="contradictions", auto_resolve=True, job_id="job-456")
    calls = [c.args for c in audit.record_audit_event.await_args_list]
    assert ("job-456", "contradiction_found", {"slug": "p1"}) in calls
    assert ("job-456", "auto_resolved", {"slug": "p1"}) in calls
