# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import asyncio
import pytest
from unittest.mock import AsyncMock
from synthadoc.agents.query_agent import QueryAgent, QueryResult
from synthadoc.providers.base import CompletionResponse
from synthadoc.storage.wiki import WikiStorage, WikiPage
from synthadoc.storage.search import HybridSearch


def _make_agent(tmp_wiki, answer_text="The answer.", decompose_json='["term"]'):
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = AsyncMock()
    provider.complete.side_effect = [
        CompletionResponse(text=decompose_json, input_tokens=10, output_tokens=5),
        CompletionResponse(text=answer_text, input_tokens=100, output_tokens=30),
    ]
    return store, search, provider


# ── decompose() unit tests ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_decompose_returns_sub_questions(tmp_wiki):
    """decompose() must return a list of 1-4 non-empty strings."""
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text='["Who invented FORTRAN?", "What influence did FORTRAN have?"]',
        input_tokens=20, output_tokens=10,
    )
    agent = QueryAgent(provider=provider, store=store, search=search)
    sub_qs = await agent.decompose("Who invented FORTRAN and what influence did it have?")
    assert isinstance(sub_qs, list)
    assert 1 <= len(sub_qs) <= 4
    assert all(isinstance(q, str) and q.strip() for q in sub_qs)


@pytest.mark.asyncio
async def test_decompose_invalid_json_falls_back_to_original(tmp_wiki):
    """If LLM returns non-JSON, decompose() must return [original_question]."""
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text="not valid json", input_tokens=10, output_tokens=5,
    )
    agent = QueryAgent(provider=provider, store=store, search=search)
    sub_qs = await agent.decompose("What is Moore's Law?")
    assert sub_qs == ["What is Moore's Law?"]


@pytest.mark.asyncio
async def test_decompose_empty_list_falls_back_to_original(tmp_wiki):
    """If LLM returns an empty list, decompose() must return [original_question]."""
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text='[]', input_tokens=10, output_tokens=5,
    )
    agent = QueryAgent(provider=provider, store=store, search=search)
    sub_qs = await agent.decompose("What is Moore's Law?")
    assert sub_qs == ["What is Moore's Law?"]


@pytest.mark.asyncio
async def test_decompose_non_list_json_falls_back_to_original(tmp_wiki):
    """If LLM returns valid JSON but not a list (e.g. a dict), fall back to [original_question]."""
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text='{"question": "What is Moore\'s Law?"}', input_tokens=10, output_tokens=5,
    )
    agent = QueryAgent(provider=provider, store=store, search=search)
    sub_qs = await agent.decompose("What is Moore's Law?")
    assert sub_qs == ["What is Moore's Law?"]


@pytest.mark.asyncio
async def test_decompose_caps_at_four_sub_questions(tmp_wiki):
    """If LLM returns more than 4 sub-questions, only the first 4 are kept."""
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text='["Q1?", "Q2?", "Q3?", "Q4?", "Q5?", "Q6?"]',
        input_tokens=10, output_tokens=10,
    )
    agent = QueryAgent(provider=provider, store=store, search=search)
    sub_qs = await agent.decompose("complex multi-part question")
    assert len(sub_qs) == 4


@pytest.mark.asyncio
async def test_decompose_filters_whitespace_only_strings(tmp_wiki):
    """Empty or whitespace-only strings in LLM output must be filtered out."""
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text='["valid sub-question?", "", "   "]',
        input_tokens=10, output_tokens=5,
    )
    agent = QueryAgent(provider=provider, store=store, search=search)
    sub_qs = await agent.decompose("something")
    assert sub_qs == ["valid sub-question?"]


@pytest.mark.asyncio
async def test_decompose_strips_markdown_code_fences(tmp_wiki):
    """Some models wrap JSON in ```json fences even when asked not to — must still parse correctly."""
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text='```json\n["Who invented FORTRAN?", "What influence did it have?"]\n```',
        input_tokens=10, output_tokens=10,
    )
    agent = QueryAgent(provider=provider, store=store, search=search)
    sub_qs = await agent.decompose("Who invented FORTRAN and what influence did it have?")
    assert len(sub_qs) == 2
    assert all(q.strip() for q in sub_qs)


@pytest.mark.asyncio
async def test_decompose_single_item_list(tmp_wiki):
    """A simple question should produce a single-element list and work end-to-end."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("moores-law", WikiPage(title="Moore's Law", tags=["hardware"],
        content="Moore's Law states transistor count doubles every two years.",
        status="active", confidence="high", sources=[]))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = AsyncMock()
    provider.complete.side_effect = [
        CompletionResponse(text='["What is Moore\'s Law?"]', input_tokens=10, output_tokens=5),
        CompletionResponse(text="Moore's Law states transistor count doubles.",
                           input_tokens=100, output_tokens=20),
    ]
    agent = QueryAgent(provider=provider, store=store, search=search)
    result = await agent.query("What is Moore's Law?")
    assert isinstance(result, QueryResult)
    assert result.answer
    assert result.question == "What is Moore's Law?"


# ── query() merge / dedup / edge cases ──────────────────────────────────────

@pytest.mark.asyncio
async def test_query_deduplicates_pages_across_sub_questions(tmp_wiki):
    """A page retrieved by multiple sub-questions must appear in citations exactly once."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("moores-law", WikiPage(title="Moore's Law", tags=["hardware"],
        content="Moore's Law doubles transistors every two years.",
        status="active", confidence="high", sources=[]))
    # Two extra pages required so BM25 IDF is positive (N≥3, term in 1 doc)
    store.write_page("unrelated-a", WikiPage(title="Unrelated A", tags=[],
        content="The quick brown fox jumps over the lazy dog.",
        status="active", confidence="high", sources=[]))
    store.write_page("unrelated-b", WikiPage(title="Unrelated B", tags=[],
        content="Propane grills require annual cleaning of burners.",
        status="active", confidence="high", sources=[]))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = AsyncMock()
    provider.complete.side_effect = [
        # Both sub-questions will hit the same page
        CompletionResponse(
            text='["Moore\'s Law transistors", "Moore\'s Law hardware impact"]',
            input_tokens=10, output_tokens=10,
        ),
        CompletionResponse(text="Moore's Law answer.", input_tokens=100, output_tokens=20),
    ]
    agent = QueryAgent(provider=provider, store=store, search=search)
    result = await agent.query("How does Moore's Law relate to hardware?")
    assert result.citations.count("moores-law") == 1


@pytest.mark.asyncio
async def test_query_merged_results_respect_top_n(tmp_wiki):
    """Merged candidates from all sub-searches must be capped at top_n."""
    store = WikiStorage(tmp_wiki / "wiki")
    for i in range(12):
        store.write_page(f"page-{i}", WikiPage(
            title=f"Page {i}", tags=[],
            content=f"content topic alpha beta gamma delta {i}",
            status="active", confidence="high", sources=[]))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = AsyncMock()
    provider.complete.side_effect = [
        CompletionResponse(
            text='["alpha beta", "gamma delta"]',
            input_tokens=10, output_tokens=10,
        ),
        CompletionResponse(text="answer", input_tokens=100, output_tokens=10),
    ]
    agent = QueryAgent(provider=provider, store=store, search=search, top_n=5)
    result = await agent.query("alpha gamma question?")
    assert len(result.citations) <= 5


@pytest.mark.asyncio
async def test_query_all_sub_searches_return_empty(tmp_wiki):
    """When no pages match any sub-question, answer call must still be made with empty context."""
    store = WikiStorage(tmp_wiki / "wiki")
    # No pages written — empty wiki
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = AsyncMock()
    provider.complete.side_effect = [
        CompletionResponse(text='["sub-q one?", "sub-q two?"]',
                           input_tokens=10, output_tokens=5),
        CompletionResponse(text="I don't know.", input_tokens=50, output_tokens=10),
    ]
    agent = QueryAgent(provider=provider, store=store, search=search)
    result = await agent.query("something not in wiki?")
    assert result.answer == "I don't know."
    assert result.citations == []


@pytest.mark.asyncio
async def test_query_result_preserves_original_question(tmp_wiki):
    """QueryResult.question must be the original full question, not any sub-question."""
    store, search, provider = _make_agent(tmp_wiki)
    agent = QueryAgent(provider=provider, store=store, search=search)
    original = "Who invented FORTRAN and what influence did it have?"
    result = await agent.query(original)
    assert result.question == original


@pytest.mark.asyncio
async def test_query_tokens_used_is_answer_call_tokens(tmp_wiki):
    """tokens_used must equal the answer LLM call tokens only."""
    store, search, provider = _make_agent(tmp_wiki)
    provider.complete.side_effect = [
        CompletionResponse(text='["term"]', input_tokens=10, output_tokens=5),   # decompose
        CompletionResponse(text="Answer.", input_tokens=100, output_tokens=25),  # answer
    ]
    agent = QueryAgent(provider=provider, store=store, search=search)
    result = await agent.query("test question")
    assert result.tokens_used == 125  # answer call only: 100 + 25


# ── existing tests (unchanged behaviour) ─────────────────────────────────────

@pytest.mark.asyncio
async def test_query_returns_answer(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("transformers", WikiPage(title="Transformers", tags=["ai"],
        content="Transformers use self-attention.", status="active",
        confidence="high", sources=[]))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text="Transformers use self-attention.", input_tokens=200, output_tokens=30)
    agent = QueryAgent(provider=provider, store=store, search=search)
    result = await agent.query("How do transformers work?")
    assert isinstance(result, QueryResult)
    assert result.answer


@pytest.mark.asyncio
async def test_query_empty_wiki_returns_answer(tmp_wiki):
    store, search, provider = _make_agent(tmp_wiki, answer_text="I don't know.")
    agent = QueryAgent(provider=provider, store=store, search=search)
    result = await agent.query("What is the meaning of life?")
    assert isinstance(result, QueryResult)
    assert result.answer == "I don't know."
    assert result.citations == []


@pytest.mark.asyncio
async def test_query_citations_match_search_results(tmp_wiki):
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
    provider = AsyncMock()
    provider.complete.side_effect = [
        CompletionResponse(text='["chlorine pool algae"]', input_tokens=10, output_tokens=5),
        CompletionResponse(text="Use chlorine shock.", input_tokens=100, output_tokens=20),
    ]
    agent = QueryAgent(provider=provider, store=store, search=search)
    result = await agent.query("How do I treat algae?")
    assert "pool-chemicals" in result.citations


@pytest.mark.asyncio
async def test_query_multiple_pages_all_cited(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    for slug, title, content in [
        ("pool-ph", "Pool pH", "pH should be 7.2 to 7.6"),
        ("pool-chlorine", "Pool Chlorine", "Free chlorine 1-3 ppm"),
        ("pool-alkalinity", "Pool Alkalinity", "Total alkalinity 80-120 ppm"),
    ]:
        store.write_page(slug, WikiPage(title=title, tags=["pool"], content=content,
                         status="active", confidence="high", sources=[]))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = AsyncMock()
    provider.complete.side_effect = [
        CompletionResponse(text='["pool ph chlorine alkalinity"]',
                           input_tokens=10, output_tokens=5),
        CompletionResponse(text="Balance pH, chlorine, and alkalinity.",
                           input_tokens=200, output_tokens=30),
    ]
    agent = QueryAgent(provider=provider, store=store, search=search)
    result = await agent.query("How do I balance pool chemistry?")
    assert len(result.citations) >= 1
    for slug in result.citations:
        assert store.page_exists(slug)


# ── compound query integration ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_compound_query_retrieves_both_parts(tmp_wiki):
    """A two-part question must retrieve pages relevant to each part independently."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("fortran-history", WikiPage(
        title="FORTRAN History", tags=["programming"],
        content="FORTRAN was invented by John Backus at IBM in 1957.",
        status="active", confidence="high", sources=[]))
    store.write_page("bombe-machine", WikiPage(
        title="Bombe Machine", tags=["ww2"],
        content="The Bombe was an electromechanical device used by Alan Turing to decrypt Enigma.",
        status="active", confidence="high", sources=[]))
    store.write_page("unrelated-page", WikiPage(
        title="Unrelated", tags=[],
        content="The quick brown fox jumps over the lazy dog.",
        status="active", confidence="high", sources=[]))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = AsyncMock()
    provider.complete.side_effect = [
        CompletionResponse(
            text='["Who invented FORTRAN?", "What was the Bombe machine?"]',
            input_tokens=20, output_tokens=15,
        ),
        CompletionResponse(
            text="FORTRAN was by Backus. Bombe was by Turing.",
            input_tokens=200, output_tokens=30,
        ),
    ]
    agent = QueryAgent(provider=provider, store=store, search=search)
    result = await agent.query("Who invented FORTRAN and what was the Bombe machine?")
    assert "fortran-history" in result.citations
    assert "bombe-machine" in result.citations


# ── performance: parallelism ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_subquestions_retrieved_in_parallel(tmp_wiki):
    """query() must call asyncio.gather() with all sub-question coroutines, not a sequential loop."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("fortran-history", WikiPage(title="FORTRAN History", tags=[],
        content="FORTRAN was invented by John Backus.", status="active",
        confidence="high", sources=[]))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = AsyncMock()
    provider.complete.side_effect = [
        CompletionResponse(text='["FORTRAN Backus", "FORTRAN IBM 1957"]',
                           input_tokens=10, output_tokens=10),
        CompletionResponse(text="FORTRAN answer.", input_tokens=100, output_tokens=20),
    ]

    gather_calls: list = []
    original_gather = asyncio.gather

    async def spy_gather(*coros, **kw):
        gather_calls.append(len(coros))
        return await original_gather(*coros, **kw)

    import unittest.mock
    with unittest.mock.patch("synthadoc.agents.query_agent.asyncio.gather", spy_gather):
        agent = QueryAgent(provider=provider, store=store, search=search)
        await agent.query("Who invented FORTRAN at IBM?")

    assert len(gather_calls) == 1, "asyncio.gather must be called exactly once per query"
    assert gather_calls[0] == 2, "both sub-questions must be passed to gather together"
