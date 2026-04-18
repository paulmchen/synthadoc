# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from synthadoc.providers.base import CompletionResponse
from synthadoc.skills.base import ExtractedContent


async def _make_ingest_agent(tmp_wiki, provider):
    from synthadoc.agents.ingest_agent import IngestAgent
    from synthadoc.storage.wiki import WikiStorage
    from synthadoc.storage.search import HybridSearch
    from synthadoc.storage.log import AuditDB, LogWriter
    from synthadoc.core.cache import CacheManager
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()
    log = LogWriter(tmp_wiki / "log.md")
    return IngestAgent(
        provider=provider, store=store, search=search,
        log_writer=log, audit_db=audit, cache=cache,
        max_pages=10, wiki_root=tmp_wiki, cache_version="v1",
    )


def _fake_search_result(urls: list[str]) -> ExtractedContent:
    return ExtractedContent(
        text="", source_path="search for: topic",
        metadata={"child_sources": urls, "query": "topic", "results_count": len(urls)},
    )


# ── decomposition fires parallel Tavily calls ─────────────────────────────────

@pytest.mark.asyncio
async def test_web_search_fires_parallel_skill_calls(tmp_wiki):
    """IngestAgent must call skill_agent.extract() once per decomposed sub-query."""
    provider = AsyncMock()
    # Call 1: SearchDecomposeAgent → 3 sub-queries
    provider.complete.return_value = CompletionResponse(
        text='["query A", "query B", "query C"]',
        input_tokens=10, output_tokens=10,
    )
    agent = await _make_ingest_agent(tmp_wiki, provider)

    call_log: list[str] = []

    async def fake_extract(source: str) -> ExtractedContent:
        call_log.append(source)
        return _fake_search_result([f"https://example.com/{len(call_log)}"])

    with patch.object(agent._skill_agent, "extract", side_effect=fake_extract):
        result = await agent.ingest("search for: Canadian gardening")

    assert len(call_log) == 3
    assert all("search for:" in c for c in call_log)
    assert "query A" in call_log[0]
    assert "query B" in call_log[1]
    assert "query C" in call_log[2]


@pytest.mark.asyncio
async def test_web_search_deduplicates_urls_across_results(tmp_wiki):
    """URLs returned by multiple sub-searches must be deduplicated."""
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text='["query A", "query B"]', input_tokens=10, output_tokens=10,
    )
    agent = await _make_ingest_agent(tmp_wiki, provider)

    call_count = 0

    async def fake_extract(source: str) -> ExtractedContent:
        nonlocal call_count
        call_count += 1
        # Both sub-searches return an overlapping URL
        return _fake_search_result([
            "https://shared.com/page",          # duplicate across both
            f"https://unique.com/{call_count}",  # unique per sub-search
        ])

    with patch.object(agent._skill_agent, "extract", side_effect=fake_extract):
        result = await agent.ingest("search for: Canadian gardening")

    # 1 shared + 2 unique = 3 total (not 4)
    assert len(result.child_sources) == 3
    assert result.child_sources.count("https://shared.com/page") == 1


@pytest.mark.asyncio
async def test_web_search_preserves_url_order(tmp_wiki):
    """First-seen URL wins; order is preserved (first sub-search URLs come first)."""
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text='["query A", "query B"]', input_tokens=10, output_tokens=10,
    )
    agent = await _make_ingest_agent(tmp_wiki, provider)

    async def fake_extract(source: str) -> ExtractedContent:
        if "query A" in source:
            return _fake_search_result(["https://a.com/1", "https://a.com/2"])
        return _fake_search_result(["https://b.com/1", "https://a.com/1"])  # a.com/1 is duplicate

    with patch.object(agent._skill_agent, "extract", side_effect=fake_extract):
        result = await agent.ingest("search for: topic")

    assert result.child_sources[0] == "https://a.com/1"
    assert result.child_sources[1] == "https://a.com/2"
    assert result.child_sources[2] == "https://b.com/1"
    assert len(result.child_sources) == 3


@pytest.mark.asyncio
async def test_non_web_search_source_not_decomposed(tmp_wiki):
    """A regular file source must not trigger search decomposition."""
    import itertools
    provider = AsyncMock()
    # Provide valid JSON for analysis and decision passes so ingest can complete
    _analysis = CompletionResponse(
        text='{"entities":["gardening"],"tags":["garden"],"summary":"gardening content","relevant":true}',
        input_tokens=10, output_tokens=10,
    )
    _decision = CompletionResponse(
        text='{"action":"create","target":"","new_slug":"test-gardening","update_content":"","page_content":"# Test\n\nContent."}',
        input_tokens=10, output_tokens=10,
    )
    provider.complete.side_effect = itertools.cycle([_analysis, _decision])
    agent = await _make_ingest_agent(tmp_wiki, provider)

    fake_md = tmp_wiki / "wiki" / "test.md"
    fake_md.write_text("# Test\nSome content about gardening.", encoding="utf-8")

    # Patch extract so it returns plain text (not child_sources)
    plain_content = ExtractedContent(text="Some content.", source_path=str(fake_md), metadata={})
    with patch.object(agent._skill_agent, "extract", return_value=plain_content):
        with patch("synthadoc.agents.ingest_agent.SearchDecomposeAgent") as mock_cls:
            await agent.ingest(str(fake_md))

    mock_cls.assert_not_called()


@pytest.mark.asyncio
async def test_web_search_fallback_single_query_still_works(tmp_wiki):
    """If decompose returns [query] (fallback), a single Tavily call must still fire."""
    provider = AsyncMock()
    # decompose falls back → returns single item
    provider.complete.side_effect = RuntimeError("LLM unavailable")
    agent = await _make_ingest_agent(tmp_wiki, provider)

    call_log: list[str] = []

    async def fake_extract(source: str) -> ExtractedContent:
        call_log.append(source)
        return _fake_search_result(["https://example.com/1"])

    with patch.object(agent._skill_agent, "extract", side_effect=fake_extract):
        result = await agent.ingest("search for: Canadian gardening")

    assert len(call_log) == 1
    assert len(result.child_sources) == 1


# ── performance ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_web_search_gather_arity_matches_decompose_count(tmp_wiki):
    """asyncio.gather() must receive exactly N coroutines for N sub-queries."""
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text='["q1", "q2", "q3"]', input_tokens=10, output_tokens=10,
    )
    agent = await _make_ingest_agent(tmp_wiki, provider)

    gather_arities: list[int] = []
    original_gather = asyncio.gather

    async def spy_gather(*coros, **kw):
        gather_arities.append(len(coros))
        return await original_gather(*coros, **kw)

    async def fake_extract(source: str) -> ExtractedContent:
        return _fake_search_result([f"https://example.com/{source[-1]}"])

    with patch.object(agent._skill_agent, "extract", side_effect=fake_extract):
        with patch("synthadoc.agents.ingest_agent.asyncio.gather", spy_gather):
            await agent.ingest("search for: topic")

    assert gather_arities == [3]


@pytest.mark.asyncio
async def test_search_decompose_called_exactly_once_per_ingest(tmp_wiki):
    """SearchDecomposeAgent.decompose() must be called exactly once per ingest."""
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text='["q1", "q2"]', input_tokens=10, output_tokens=10,
    )
    agent = await _make_ingest_agent(tmp_wiki, provider)

    decompose_calls: list[str] = []
    original_decompose_cls = __import__(
        "synthadoc.agents.search_decompose_agent", fromlist=["SearchDecomposeAgent"]
    ).SearchDecomposeAgent

    class SpyDecomposeAgent(original_decompose_cls):
        async def decompose(self, query: str) -> list[str]:
            decompose_calls.append(query)
            return await super().decompose(query)

    async def fake_extract(source: str) -> ExtractedContent:
        return _fake_search_result([f"https://example.com/1"])

    with patch("synthadoc.agents.ingest_agent.SearchDecomposeAgent", SpyDecomposeAgent):
        with patch.object(agent._skill_agent, "extract", side_effect=fake_extract):
            await agent.ingest("search for: Canadian gardening")

    assert len(decompose_calls) == 1
    assert decompose_calls[0] == "Canadian gardening"
