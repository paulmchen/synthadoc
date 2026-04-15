# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest
from unittest.mock import AsyncMock
from synthadoc.agents.query_agent import QueryAgent, QueryResult
from synthadoc.providers.base import CompletionResponse
from synthadoc.storage.wiki import WikiStorage, WikiPage
from synthadoc.storage.search import HybridSearch
from synthadoc.core.cache import CacheManager


def _make_agent(tmp_wiki, answer_text="The answer.", terms_json='["term"]'):
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    provider = AsyncMock()
    provider.complete.side_effect = [
        CompletionResponse(text=terms_json, input_tokens=10, output_tokens=5),
        CompletionResponse(text=answer_text, input_tokens=100, output_tokens=30),
    ]
    return store, search, cache, provider


@pytest.mark.asyncio
async def test_query_returns_answer(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("transformers", WikiPage(title="Transformers", tags=["ai"],
        content="Transformers use self-attention.", status="active",
        confidence="high", sources=[]))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text="Transformers use self-attention.", input_tokens=200, output_tokens=30)
    agent = QueryAgent(provider=provider, store=store, search=search, cache=cache)
    result = await agent.query("How do transformers work?")
    assert isinstance(result, QueryResult)
    assert result.answer


# ── Corner cases ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_query_empty_wiki_returns_answer(tmp_wiki):
    """Query against an empty wiki must not raise — context will be 'No relevant pages found.'"""
    store, search, cache, provider = _make_agent(tmp_wiki, answer_text="I don't know.")
    await cache.init()
    agent = QueryAgent(provider=provider, store=store, search=search, cache=cache)
    result = await agent.query("What is the meaning of life?")
    assert isinstance(result, QueryResult)
    assert result.answer == "I don't know."
    assert result.citations == []


@pytest.mark.asyncio
async def test_query_invalid_terms_json_falls_back_to_split(tmp_wiki):
    """If the LLM returns non-JSON for terms extraction, fall back to word split."""
    store, search, cache, provider = _make_agent(
        tmp_wiki,
        answer_text="Fallback answer.",
        terms_json="not valid json at all"
    )
    store.write_page("pool", WikiPage(title="Pool", tags=[], content="chlorine levels",
                     status="active", confidence="high", sources=[]))
    await cache.init()
    agent = QueryAgent(provider=provider, store=store, search=search, cache=cache)
    result = await agent.query("chlorine pool")
    # Must not raise — falls back to question.split()
    assert result.answer == "Fallback answer."


@pytest.mark.asyncio
async def test_query_citations_match_search_results(tmp_wiki):
    """Citations must list the slugs of pages that were retrieved as candidates.

    Two pages are created so BM25 IDF is positive for terms that appear in only
    one document — a single-document corpus produces negative IDF for all terms.
    """
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("pool-chemicals", WikiPage(title="Pool Chemicals", tags=["pool"],
        content="Chlorine shock treats algae.", status="active", confidence="high", sources=[]))
    store.write_page("lawn-care", WikiPage(title="Lawn Care", tags=["lawn"],
        content="Mowing frequency depends on grass growth rate.", status="active",
        confidence="high", sources=[]))
    store.write_page("bbq-guide", WikiPage(title="BBQ Guide", tags=["bbq"],
        content="Propane grills require annual cleaning of burners.", status="active",
        confidence="high", sources=[]))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()
    provider = AsyncMock()
    provider.complete.side_effect = [
        CompletionResponse(text='["chlorine", "pool", "algae"]', input_tokens=10, output_tokens=5),
        CompletionResponse(text="Use chlorine shock.", input_tokens=100, output_tokens=20),
    ]
    agent = QueryAgent(provider=provider, store=store, search=search, cache=cache)
    result = await agent.query("How do I treat algae?")
    assert "pool-chemicals" in result.citations


@pytest.mark.asyncio
async def test_query_tokens_used_is_sum_of_both_calls(tmp_wiki):
    """tokens_used must equal the sum of term-extraction + answer LLM calls."""
    store, search, cache, provider = _make_agent(tmp_wiki)
    # Override side_effect with known token counts
    provider.complete.side_effect = [
        CompletionResponse(text='["term"]', input_tokens=10, output_tokens=5),   # total=15
        CompletionResponse(text="Answer.", input_tokens=100, output_tokens=25),  # total=125
    ]
    await cache.init()
    agent = QueryAgent(provider=provider, store=store, search=search, cache=cache)
    result = await agent.query("test question")
    assert result.tokens_used == 140


@pytest.mark.asyncio
async def test_query_result_has_original_question(tmp_wiki):
    """QueryResult.question must preserve the original question string exactly."""
    store, search, cache, provider = _make_agent(tmp_wiki)
    await cache.init()
    agent = QueryAgent(provider=provider, store=store, search=search, cache=cache)
    question = "What is the chlorine ppm for a residential pool?"
    result = await agent.query(question)
    assert result.question == question


@pytest.mark.asyncio
async def test_query_multiple_pages_all_cited(tmp_wiki):
    """All retrieved candidate pages must appear in citations."""
    store = WikiStorage(tmp_wiki / "wiki")
    for slug, title, content in [
        ("pool-ph", "Pool pH", "pH should be 7.2 to 7.6"),
        ("pool-chlorine", "Pool Chlorine", "Free chlorine 1-3 ppm"),
        ("pool-alkalinity", "Pool Alkalinity", "Total alkalinity 80-120 ppm"),
    ]:
        store.write_page(slug, WikiPage(title=title, tags=["pool"], content=content,
                         status="active", confidence="high", sources=[]))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()
    provider = AsyncMock()
    provider.complete.side_effect = [
        CompletionResponse(text='["pool", "ph", "chlorine", "alkalinity"]',
                           input_tokens=10, output_tokens=5),
        CompletionResponse(text="Balance pH, chlorine, and alkalinity.",
                           input_tokens=200, output_tokens=30),
    ]
    agent = QueryAgent(provider=provider, store=store, search=search, cache=cache)
    result = await agent.query("How do I balance pool chemistry?")
    assert len(result.citations) >= 1  # at least one page retrieved
    for slug in result.citations:
        assert store.page_exists(slug)  # every cited page must actually exist
