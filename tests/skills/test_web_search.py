# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest
from unittest.mock import AsyncMock, patch


def _make_tavily_response(n: int = 3) -> dict:
    return {
        "results": [
            {"url": f"https://example.com/article-{i}",
             "content": f"Content {i}", "title": f"Article {i}"}
            for i in range(n)
        ]
    }


@pytest.mark.asyncio
async def test_web_search_extract_returns_child_sources(monkeypatch):
    """WebSearchSkill.extract() returns child_sources URLs from Tavily."""
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    monkeypatch.setenv("SYNTHADOC_WEB_SEARCH_MAX_RESULTS", "5")

    from synthadoc.skills.web_search.scripts.main import WebSearchSkill
    from synthadoc.skills.web_search.scripts import fetcher

    with patch.object(fetcher, "search_tavily",
                      new=AsyncMock(return_value=_make_tavily_response(3))):
        skill = WebSearchSkill()
        result = await skill.extract("search for: quantum computing")

    assert result.metadata.get("child_sources") is not None
    assert len(result.metadata["child_sources"]) == 3
    assert all(u.startswith("https://") for u in result.metadata["child_sources"])
    assert result.text == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("source,expected_query", [
    ("search for: quantum computing",        "quantum computing"),
    ("search for quantum computing",         "quantum computing"),   # no colon
    ("Search For: Quantum Computing",        "Quantum Computing"),   # mixed case
    ("look up: Dennis Ritchie",              "Dennis Ritchie"),
    ("look up Dennis Ritchie",               "Dennis Ritchie"),
    ("find on the web: AGPL licence",        "AGPL licence"),
    ("web search: neural networks",          "neural networks"),
    ("browse: Rust async runtime",           "Rust async runtime"),
    # UTF-8 / CJK queries — intent prefix is English, query can be any language
    ("search for: 量子计算",                  "量子计算"),
    ("look up: 德尼斯·里奇",                  "德尼斯·里奇"),
    ("browse: Rustの非同期ランタイム",         "Rustの非同期ランタイム"),
])
async def test_web_search_extracts_query_from_intent(source, expected_query, monkeypatch):
    """Intent prefix is stripped regardless of colon or capitalisation."""
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")

    from synthadoc.skills.web_search.scripts.main import WebSearchSkill
    from synthadoc.skills.web_search.scripts import fetcher

    captured_query = []

    async def capture_search(query, max_results, api_key):
        captured_query.append(query)
        return _make_tavily_response(1)

    with patch.object(fetcher, "search_tavily", side_effect=capture_search):
        await WebSearchSkill().extract(source)

    assert captured_query[0] == expected_query


@pytest.mark.asyncio
async def test_web_search_respects_max_results(monkeypatch):
    """max_results from env var is passed to Tavily."""
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    monkeypatch.setenv("SYNTHADOC_WEB_SEARCH_MAX_RESULTS", "7")

    from synthadoc.skills.web_search.scripts.main import WebSearchSkill
    from synthadoc.skills.web_search.scripts import fetcher

    captured = []

    async def capture(query, max_results, api_key):
        captured.append(max_results)
        return _make_tavily_response(7)

    with patch.object(fetcher, "search_tavily", side_effect=capture):
        skill = WebSearchSkill()
        await skill.extract("search for: test query")

    assert captured[0] == 7


def test_ingest_result_has_child_sources_field():
    """IngestResult must have a child_sources field."""
    from synthadoc.agents.ingest_agent import IngestResult
    r = IngestResult(source="search for: test")
    assert hasattr(r, "child_sources")
    assert r.child_sources == []


@pytest.mark.asyncio
async def test_ingest_agent_returns_child_sources_for_web_search(tmp_wiki, monkeypatch):
    """When extract() returns child_sources, ingest() returns them with no LLM calls."""
    from unittest.mock import AsyncMock, patch
    from synthadoc.agents.ingest_agent import IngestAgent
    from synthadoc.skills.base import ExtractedContent
    from synthadoc.storage.wiki import WikiStorage
    from synthadoc.storage.search import HybridSearch
    from synthadoc.storage.log import LogWriter, AuditDB
    from synthadoc.core.cache import CacheManager

    provider = AsyncMock()
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()

    child_urls = ["https://example.com/a", "https://example.com/b"]
    mock_extracted = ExtractedContent(
        text="", source_path="search for: test",
        metadata={"child_sources": child_urls})

    agent = IngestAgent(provider=provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)

    with patch.object(agent._skill_agent, "extract", return_value=mock_extracted):
        result = await agent.ingest("search for: test")

    assert result.child_sources == child_urls
    provider.complete.assert_not_called()


@pytest.mark.asyncio
async def test_web_search_missing_api_key_raises(monkeypatch):
    """Missing TAVILY_API_KEY raises EnvironmentError."""
    monkeypatch.setenv("TAVILY_API_KEY", "")

    from synthadoc.skills.web_search.scripts.main import WebSearchSkill
    skill = WebSearchSkill()
    with pytest.raises(EnvironmentError, match="TAVILY_API_KEY"):
        await skill.extract("search for: test")
