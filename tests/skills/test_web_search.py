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

    async def capture_search(query, max_results, api_key, include_domains=None):
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

    async def capture(query, max_results, api_key, include_domains=None):
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
    """When extract() returns child_sources, ingest() returns them after decomposition."""
    from unittest.mock import AsyncMock, patch
    from synthadoc.agents.ingest_agent import IngestAgent
    from synthadoc.providers.base import CompletionResponse
    from synthadoc.skills.base import ExtractedContent
    from synthadoc.storage.wiki import WikiStorage
    from synthadoc.storage.search import HybridSearch
    from synthadoc.storage.log import LogWriter, AuditDB
    from synthadoc.core.cache import CacheManager

    provider = AsyncMock()
    # SearchDecomposeAgent falls back to single query when decompose returns 1 item
    provider.complete.return_value = CompletionResponse(
        text='["test"]', input_tokens=5, output_tokens=5,
    )
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
    # provider.complete is called once by SearchDecomposeAgent (decomposition step)
    assert provider.complete.call_count == 1


@pytest.mark.asyncio
async def test_web_search_missing_api_key_raises(monkeypatch):
    """Missing TAVILY_API_KEY raises EnvironmentError."""
    monkeypatch.setenv("TAVILY_API_KEY", "")

    from synthadoc.skills.web_search.scripts.main import WebSearchSkill
    skill = WebSearchSkill()
    with pytest.raises(EnvironmentError, match="TAVILY_API_KEY"):
        await skill.extract("search for: test")


# ── YouTube-specific web search ───────────────────────────────────────────────

def _make_youtube_response(n: int = 2) -> dict:
    return {
        "results": [
            {"url": f"https://www.youtube.com/watch?v=vid{i}",
             "content": f"Transcript {i}", "title": f"YouTube Video {i}"}
            for i in range(n)
        ]
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("source,expected_query", [
    # The four key use cases from the design discussion
    ("youtube Moore's Law",                      "Moore's Law"),
    ("youtube video on transistors",             "on transistors"),
    ("youtube kids: Sesame Street",              "Sesame Street"),
    ("search for youtube: history of computing", "history of computing"),
    # Additional variants
    ("search youtube: Alan Turing",              "Alan Turing"),
    ("search youtube for: Grace Hopper",         "Grace Hopper"),
    ("youtube search: ENIAC",                    "ENIAC"),
    ("youtube lecture on deep learning",         "on deep learning"),
    ("youtube talk: Linus Torvalds",             "Linus Torvalds"),
    ("youtube channel: MIT OpenCourseWare",      "MIT OpenCourseWare"),
    # Mixed case
    ("YouTube Moore's Law",                      "Moore's Law"),
    ("YOUTUBE KIDS: Sesame Street",              "Sesame Street"),
    ("Search For YouTube: Ada Lovelace",         "Ada Lovelace"),
])
async def test_youtube_search_strips_prefix_from_query(source, expected_query, monkeypatch):
    """YouTube intent prefix is fully stripped; clean query is sent to Tavily."""
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")

    from synthadoc.skills.web_search.scripts.main import WebSearchSkill
    from synthadoc.skills.web_search.scripts import fetcher

    captured = []

    async def capture(query, max_results, api_key, include_domains=None):
        captured.append(query)
        return _make_youtube_response(1)

    with patch.object(fetcher, "search_tavily", side_effect=capture):
        await WebSearchSkill().extract(source)

    assert captured[0] == expected_query


@pytest.mark.asyncio
@pytest.mark.parametrize("source", [
    "youtube Moore's Law",
    "youtube video on transistors",
    "youtube kids: Sesame Street",
    "search for youtube: history of computing",
    "search youtube: Alan Turing",
    "youtube search: ENIAC",
])
async def test_youtube_search_passes_include_domains(source, monkeypatch):
    """Every YouTube intent variant passes include_domains=youtube to Tavily."""
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")

    from synthadoc.skills.web_search.scripts.main import WebSearchSkill
    from synthadoc.skills.web_search.scripts import fetcher

    captured = []

    async def capture(query, max_results, api_key, include_domains=None):
        captured.append(include_domains)
        return _make_youtube_response(1)

    with patch.object(fetcher, "search_tavily", side_effect=capture):
        await WebSearchSkill().extract(source)

    assert captured[0] is not None, "include_domains must not be None for YouTube search"
    assert "youtube.com" in captured[0]
    assert "youtu.be" in captured[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("source", [
    "search for: Moore's Law",
    "look up: Alan Turing",
    "find on the web: ENIAC history",
    "web search: Grace Hopper",
    "browse: transistor scaling",
])
async def test_generic_search_does_not_pass_include_domains(source, monkeypatch):
    """Generic web search must not pass include_domains — Tavily searches all domains."""
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")

    from synthadoc.skills.web_search.scripts.main import WebSearchSkill
    from synthadoc.skills.web_search.scripts import fetcher

    captured = []

    async def capture(query, max_results, api_key, include_domains=None):
        captured.append(include_domains)
        return _make_tavily_response(1)

    with patch.object(fetcher, "search_tavily", side_effect=capture):
        await WebSearchSkill().extract(source)

    assert captured[0] is None, f"include_domains must be None for generic search: {source!r}"


@pytest.mark.asyncio
async def test_youtube_search_returns_youtube_child_sources(monkeypatch):
    """YouTube search child_sources are all YouTube URLs."""
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")

    from synthadoc.skills.web_search.scripts.main import WebSearchSkill
    from synthadoc.skills.web_search.scripts import fetcher

    with patch.object(fetcher, "search_tavily",
                      new=AsyncMock(return_value=_make_youtube_response(3))):
        result = await WebSearchSkill().extract("youtube Moore's Law")

    assert len(result.metadata["child_sources"]) == 3
    assert all("youtube.com" in url for url in result.metadata["child_sources"])
    assert result.metadata["query"] == "Moore's Law"


@pytest.mark.asyncio
async def test_youtube_search_metadata_has_query(monkeypatch):
    """Metadata query field reflects the stripped query, not the full source."""
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")

    from synthadoc.skills.web_search.scripts.main import WebSearchSkill
    from synthadoc.skills.web_search.scripts import fetcher

    with patch.object(fetcher, "search_tavily",
                      new=AsyncMock(return_value=_make_youtube_response(1))):
        result = await WebSearchSkill().extract("search for youtube: history of computing")

    assert result.metadata["query"] == "history of computing"


# ── URL skill — non-YouTube pass-through ─────────────────────────────────────

@pytest.mark.asyncio
async def test_url_skill_still_handles_non_youtube_urls():
    """Non-YouTube URLs must still be processed normally."""
    import respx, httpx
    from synthadoc.skills.url.scripts.main import UrlSkill
    with respx.mock:
        respx.get("https://example.com/article").mock(
            return_value=httpx.Response(
                200, text="<html><body><p>Article content</p></body></html>")
        )
        result = await UrlSkill().extract("https://example.com/article")
    assert "Article content" in result.text


# ── fetcher.search_tavily unit tests ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_tavily_calls_client_with_query_and_max_results():
    """search_tavily passes query and max_results to AsyncTavilyClient.search."""
    from synthadoc.skills.web_search.scripts.fetcher import search_tavily

    mock_client = AsyncMock()
    mock_client.search.return_value = {"results": []}

    with patch("tavily.AsyncTavilyClient",
               return_value=mock_client) as mock_cls:
        result = await search_tavily("quantum computing", max_results=5, api_key="test-key")

    mock_cls.assert_called_once_with(api_key="test-key")
    mock_client.search.assert_called_once_with("quantum computing", max_results=5)
    assert result == {"results": []}


@pytest.mark.asyncio
async def test_search_tavily_passes_include_domains_when_provided():
    """include_domains is forwarded to client.search when not None."""
    from synthadoc.skills.web_search.scripts.fetcher import search_tavily

    mock_client = AsyncMock()
    mock_client.search.return_value = {"results": []}

    with patch("tavily.AsyncTavilyClient", return_value=mock_client):
        await search_tavily("Moore's Law", max_results=3, api_key="key",
                            include_domains=["youtube.com", "youtu.be"])

    _, kwargs = mock_client.search.call_args
    assert kwargs.get("include_domains") == ["youtube.com", "youtu.be"]


@pytest.mark.asyncio
async def test_search_tavily_omits_include_domains_when_none():
    """include_domains is NOT forwarded when None — Tavily searches all domains."""
    from synthadoc.skills.web_search.scripts.fetcher import search_tavily

    mock_client = AsyncMock()
    mock_client.search.return_value = {"results": []}

    with patch("tavily.AsyncTavilyClient", return_value=mock_client):
        await search_tavily("Alan Turing", max_results=5, api_key="key",
                            include_domains=None)

    _, kwargs = mock_client.search.call_args
    assert "include_domains" not in kwargs


@pytest.mark.asyncio
async def test_search_tavily_returns_raw_client_response():
    """search_tavily returns the raw dict from client.search unchanged."""
    from synthadoc.skills.web_search.scripts.fetcher import search_tavily

    expected = {"results": [{"url": "https://example.com", "content": "text"}],
                "query": "test", "response_time": 0.42}
    mock_client = AsyncMock()
    mock_client.search.return_value = expected

    with patch("tavily.AsyncTavilyClient", return_value=mock_client):
        result = await search_tavily("test", max_results=1, api_key="key")

    assert result is expected
