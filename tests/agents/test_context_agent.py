# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import asyncio
from unittest.mock import MagicMock, AsyncMock
import pytest
from synthadoc.agents.context_agent import ContextAgent, ContextPack


def _mock_search_result(slug: str, score: float, content: str):
    r = MagicMock()
    r.slug = slug
    r.score = score
    page = MagicMock()
    page.title = slug.replace("-", " ").title()
    page.content = content
    page.confidence = "high"
    page.tags = []
    r.page = page
    return r


def _make_provider(response_text: str = '["early computing"]'):
    provider = MagicMock()
    provider.complete = AsyncMock(return_value=MagicMock(
        text=response_text, input_tokens=5, output_tokens=5,
        total_tokens=10,
    ))
    return provider


@pytest.mark.asyncio
async def test_context_pack_includes_top_pages():
    provider = _make_provider('["Who was Alan Turing?"]')
    store = MagicMock()
    store.list_pages.return_value = ["alan-turing"]
    store.read_page.return_value = MagicMock(aliases=[])
    search = MagicMock()
    search.hybrid_search = AsyncMock(return_value=[
        _mock_search_result("alan-turing", 0.92, "Alan Turing " * 50)
    ])
    agent = ContextAgent(provider=provider, store=store, search=search, token_budget=500)
    pack = await agent.build("early computing pioneers")
    assert len(pack.pages) >= 1
    assert pack.pages[0].slug == "alan-turing"
    assert pack.tokens_used <= 500


@pytest.mark.asyncio
async def test_context_pack_omits_pages_over_budget():
    provider = _make_provider('["early computing"]')
    store = MagicMock()
    store.list_pages.return_value = ["page-a", "page-b"]
    long_content = "word " * 500
    def _make_page(aliases=None, content="short"):
        p = MagicMock()
        p.aliases = aliases or []
        p.content = content
        p.confidence = "high"
        p.tags = []
        return p
    store.read_page.side_effect = lambda slug: _make_page(content=long_content)
    search = MagicMock()
    search.hybrid_search = AsyncMock(return_value=[
        _mock_search_result("page-a", 0.9, long_content),
        _mock_search_result("page-b", 0.8, long_content),
    ])
    agent = ContextAgent(provider=provider, store=store, search=search, token_budget=300)
    pack = await agent.build("early computing")
    assert len(pack.pages) < 2
    assert len(pack.omitted) >= 1


@pytest.mark.asyncio
async def test_context_pack_empty_wiki():
    provider = _make_provider('["query"]')
    store = MagicMock()
    store.list_pages.return_value = []
    store.read_page.return_value = None
    search = MagicMock()
    search.hybrid_search = AsyncMock(return_value=[])
    agent = ContextAgent(provider=provider, store=store, search=search)
    pack = await agent.build("anything")
    assert pack.pages == []
    assert pack.tokens_used == 0


@pytest.mark.asyncio
async def test_context_pack_to_markdown_contains_goal():
    provider = _make_provider('["early computing"]')
    store = MagicMock()
    store.list_pages.return_value = ["alan-turing"]
    store.read_page.return_value = MagicMock(aliases=[])
    search = MagicMock()
    search.hybrid_search = AsyncMock(return_value=[
        _mock_search_result("alan-turing", 0.92, "Alan Turing pioneered computation.")
    ])
    agent = ContextAgent(provider=provider, store=store, search=search)
    pack = await agent.build("early computing pioneers")
    md = pack.to_markdown()
    assert "early computing pioneers" in md
    assert "alan-turing" in md


@pytest.mark.asyncio
async def test_context_pack_to_dict_has_required_keys():
    provider = _make_provider('["query"]')
    store = MagicMock()
    store.list_pages.return_value = []
    store.read_page.return_value = None
    search = MagicMock()
    search.hybrid_search = AsyncMock(return_value=[])
    agent = ContextAgent(provider=provider, store=store, search=search)
    pack = await agent.build("test goal")
    d = pack.to_dict()
    assert "goal" in d
    assert "token_budget" in d
    assert "tokens_used" in d
    assert "pages" in d
    assert "omitted" in d
