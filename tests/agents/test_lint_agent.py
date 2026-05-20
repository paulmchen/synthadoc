# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest
from unittest.mock import AsyncMock
from synthadoc.agents.lint_agent import LintAgent, LintReport, find_orphan_slugs, _fix_dangling_wikilinks, LINT_SKIP_SLUGS, LINT_SKIP_SOURCE_SLUGS
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


# ── Dangling link cleanup ─────────────────────────────────────────────────────

def test_fix_dangling_wikilinks_drops_list_item():
    """List item whose primary content is a dangling link is removed."""
    existing = {"alan-turing", "index"}
    content = (
        "# Index\n\n"
        "- [[alan-turing]] — pioneer\n"
        "- [[deleted-page]] — Watch\n"
        "- [[also-gone]] — old reference\n"
    )
    result = _fix_dangling_wikilinks(content, existing)
    assert "[[deleted-page]]" not in result
    assert "[[also-gone]]" not in result
    assert "[[alan-turing]]" in result


def test_fix_dangling_wikilinks_unlinks_inline():
    """Inline dangling [[link]] is replaced with plain display text."""
    existing = {"real-page"}
    content = "As described in [[gone-page]], and also in [[real-page]]."
    result = _fix_dangling_wikilinks(content, existing)
    assert "[[gone-page]]" not in result
    assert "gone-page" in result          # display text kept
    assert "[[real-page]]" in result      # existing link untouched


def test_fix_dangling_wikilinks_aliased_inline():
    """[[slug|Display Text]] strips the link notation, keeps display text."""
    existing = {"real-page"}
    content = "See [[deleted|Old Name]] for details."
    result = _fix_dangling_wikilinks(content, existing)
    assert "[[deleted|Old Name]]" not in result
    assert "Old Name" in result


@pytest.mark.asyncio
async def test_lint_removes_dangling_links(tmp_wiki):
    """Running lint cleans up [[links]] pointing to pages that no longer exist."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("index", WikiPage(title="Index", tags=[],
        content="# Index\n\n- [[alan-turing]] — pioneer\n- [[crashcourse-computer-science]] — Watch\n",
        status="active", confidence="high", sources=[]))
    store.write_page("alan-turing", WikiPage(title="Alan Turing", tags=[],
        content="Mathematician.", status="active", confidence="high", sources=[]))
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    agent = LintAgent(provider=AsyncMock(), store=store, log_writer=log)
    report = await agent.lint(scope="orphans")

    assert report.dangling_links_removed == 1
    updated = store.read_page("index")
    assert "[[crashcourse-computer-science]]" not in updated.content
    assert "[[alan-turing]]" in updated.content


# ── Adversarial pass ──────────────────────────────────────────────────────────

from synthadoc.agents.lint_agent import _parse_adversarial_response


def test_parse_adversarial_response_valid_json():
    result = _parse_adversarial_response('[{"claim": "X was the first.", "concern": "Overstated"}]')
    assert result == [{"claim": "X was the first.", "concern": "Overstated"}]


def test_parse_adversarial_response_markdown_fenced():
    result = _parse_adversarial_response(
        '```json\n[{"claim": "X", "concern": "Y"}]\n```'
    )
    assert result == [{"claim": "X", "concern": "Y"}]


def test_parse_adversarial_response_empty_list():
    assert _parse_adversarial_response("[]") == []


def test_parse_adversarial_response_invalid_returns_empty():
    assert _parse_adversarial_response("not valid json") == []


def test_parse_adversarial_response_skips_entries_without_concern():
    result = _parse_adversarial_response('[{"claim": "X", "concern": ""}, {"claim": "Y", "concern": "Valid"}]')
    assert len(result) == 1
    assert result[0]["claim"] == "Y"


@pytest.mark.asyncio
async def test_adversarial_pass_stores_warnings(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("ai-page", WikiPage(
        title="AI", tags=[], content="Transformers replaced RNNs entirely by 2020.",
        status="active", confidence="high", sources=[]))
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    adv_provider = AsyncMock()
    adv_provider.complete.return_value = CompletionResponse(
        text='[{"claim": "Transformers replaced RNNs entirely by 2020.", "concern": "Overstated"}]',
        input_tokens=100, output_tokens=50,
    )
    agent = LintAgent(
        provider=AsyncMock(), store=store, log_writer=log,
        adversarial_provider=adv_provider,
    )
    report = await agent.lint(adversarial=True)
    page = store.read_page("ai-page")
    assert len(page.lint_warnings) == 1
    assert page.lint_warnings[0]["claim"] == "Transformers replaced RNNs entirely by 2020."
    assert len(report.adversarial_warnings) == 1
    assert report.adversarial_warnings[0]["slug"] == "ai-page"


@pytest.mark.asyncio
async def test_adversarial_pass_no_warnings_on_clean_page(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("clean", WikiPage(
        title="Clean", tags=[], content="Well-cited facts.",
        status="active", confidence="high", sources=[]))
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    adv_provider = AsyncMock()
    adv_provider.complete.return_value = CompletionResponse(
        text="[]", input_tokens=10, output_tokens=2,
    )
    agent = LintAgent(
        provider=AsyncMock(), store=store, log_writer=log,
        adversarial_provider=adv_provider,
    )
    report = await agent.lint(adversarial=True)
    assert store.read_page("clean").lint_warnings == []
    assert report.adversarial_warnings == []


@pytest.mark.asyncio
async def test_adversarial_pass_rate_limit_is_non_fatal(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("p1", WikiPage(
        title="P1", tags=[], content="Claim one.",
        status="active", confidence="high", sources=[]))
    store.write_page("p2", WikiPage(
        title="P2", tags=[], content="Claim two.",
        status="active", confidence="high", sources=[]))
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    adv_provider = AsyncMock()
    adv_provider.complete.side_effect = [
        Exception("429 Too Many Requests"),
        CompletionResponse(
            text='[{"claim": "Claim two.", "concern": "Unsupported"}]',
            input_tokens=50, output_tokens=20,
        ),
    ]
    agent = LintAgent(
        provider=AsyncMock(), store=store, log_writer=log,
        adversarial_provider=adv_provider,
    )
    report = await agent.lint(adversarial=True)
    p1 = store.read_page("p1")
    p2 = store.read_page("p2")
    assert p1.lint_warnings[0]["claim"] is None
    assert "rate limit" in p1.lint_warnings[0]["concern"]
    assert p2.lint_warnings[0]["claim"] == "Claim two."


@pytest.mark.asyncio
async def test_no_adversarial_clears_existing_warnings(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    page = WikiPage(
        title="P", tags=[], content="Content.", status="active", confidence="high",
        sources=[], lint_warnings=[{"claim": "Old claim", "concern": "Old concern"}],
    )
    store.write_page("p", page)
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    agent = LintAgent(provider=AsyncMock(), store=store, log_writer=log)
    await agent.lint(adversarial=False)
    assert store.read_page("p").lint_warnings == []


@pytest.mark.asyncio
async def test_adversarial_pass_uses_adversarial_provider(tmp_wiki):
    """When adversarial_provider is set, it is used for adversarial calls, not self._provider."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("p", WikiPage(
        title="P", tags=[], content="Some content.",
        status="active", confidence="high", sources=[]))
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    lint_provider = AsyncMock()
    adv_provider = AsyncMock()
    adv_provider.complete.return_value = CompletionResponse(
        text="[]", input_tokens=5, output_tokens=1,
    )
    agent = LintAgent(
        provider=lint_provider, store=store, log_writer=log,
        adversarial_provider=adv_provider,
    )
    await agent.lint(adversarial=True)
    # adv_provider called; lint_provider not called (no contradictions, no auto-resolve)
    adv_provider.complete.assert_called_once()
    lint_provider.complete.assert_not_called()


@pytest.mark.asyncio
async def test_adversarial_pass_skip_slugs_not_evaluated(tmp_wiki):
    """LINT_SKIP_SLUGS pages (index, log, dashboard) are never adversarially reviewed."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("index", WikiPage(
        title="Index", tags=[], content="# Index", status="active", confidence="high", sources=[]))
    store.write_page("real-page", WikiPage(
        title="Real", tags=[], content="Real content.", status="active", confidence="high", sources=[]))
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    adv_provider = AsyncMock()
    adv_provider.complete.return_value = CompletionResponse(text="[]", input_tokens=5, output_tokens=1)
    agent = LintAgent(
        provider=AsyncMock(), store=store, log_writer=log,
        adversarial_provider=adv_provider,
    )
    await agent.lint(adversarial=True)
    # Only real-page evaluated (1 call), not index
    assert adv_provider.complete.call_count == 1
