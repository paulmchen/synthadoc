# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from synthadoc.agents.query_agent import QueryAgent, QueryResult
from synthadoc.providers.base import CompletionResponse
from synthadoc.storage.wiki import WikiStorage, WikiPage
from synthadoc.storage.search import HybridSearch, SearchResult


def _make_agent(tmp_wiki, answer_text="The answer.", decompose_json='["term"]'):
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = AsyncMock()
    provider.complete.side_effect = [
        CompletionResponse(text=decompose_json, input_tokens=10, output_tokens=5),
        CompletionResponse(text=answer_text, input_tokens=100, output_tokens=30),
    ]
    return store, search, provider


def _make_agent_no_gap(tmp_wiki, **kw):
    """Like _make_agent but disables gap detection (gap_score_threshold=0.0)."""
    store, search, provider = _make_agent(tmp_wiki, **kw)
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
    agent = QueryAgent(provider=provider, store=store, search=search,
                       gap_score_threshold=0.0)
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
    agent = QueryAgent(provider=provider, store=store, search=search,
                       gap_score_threshold=0.0)
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
    agent = QueryAgent(provider=provider, store=store, search=search, top_n=5,
                       gap_score_threshold=0.0)
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
    agent = QueryAgent(provider=provider, store=store, search=search,
                       gap_score_threshold=0.0)
    result = await agent.query("something not in wiki?")
    assert result.answer == "I don't know."
    assert result.citations == []


@pytest.mark.asyncio
async def test_query_result_preserves_original_question(tmp_wiki):
    """QueryResult.question must be the original full question, not any sub-question."""
    store, search, provider = _make_agent(tmp_wiki)
    agent = QueryAgent(provider=provider, store=store, search=search,
                       gap_score_threshold=0.0)
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
    agent = QueryAgent(provider=provider, store=store, search=search,
                       gap_score_threshold=0.0)
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
    agent = QueryAgent(provider=provider, store=store, search=search,
                       gap_score_threshold=0.0)
    result = await agent.query("How do transformers work?")
    assert isinstance(result, QueryResult)
    assert result.answer


@pytest.mark.asyncio
async def test_query_empty_wiki_returns_answer(tmp_wiki):
    store, search, provider = _make_agent(tmp_wiki, answer_text="I don't know.")
    agent = QueryAgent(provider=provider, store=store, search=search,
                       gap_score_threshold=0.0)
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
    agent = QueryAgent(provider=provider, store=store, search=search,
                       gap_score_threshold=0.0)
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
    agent = QueryAgent(provider=provider, store=store, search=search,
                       gap_score_threshold=0.0)
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
    agent = QueryAgent(provider=provider, store=store, search=search,
                       gap_score_threshold=0.0)
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
        agent = QueryAgent(provider=provider, store=store, search=search,
                           gap_score_threshold=0.0)
        await agent.query("Who invented FORTRAN at IBM?")

    assert len(gather_calls) == 1, "asyncio.gather must be called exactly once per query"
    assert gather_calls[0] == 2, "both sub-questions must be passed to gather together"


# ── decompose() edge cases ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_decompose_provider_exception_falls_back(tmp_wiki):
    """If the provider raises any exception, decompose() must return [question]."""
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = AsyncMock()
    provider.complete.side_effect = RuntimeError("network error")
    agent = QueryAgent(provider=provider, store=store, search=search)
    result = await agent.decompose("What is Moore's Law?")
    assert result == ["What is Moore's Law?"]


@pytest.mark.asyncio
async def test_decompose_truncates_long_question(tmp_wiki):
    """Questions longer than 4000 chars must be truncated before the LLM call."""
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text='["short sub-question"]', input_tokens=5, output_tokens=5
    )
    agent = QueryAgent(provider=provider, store=store, search=search)
    long_question = "x" * 5000
    await agent.decompose(long_question)
    called_content = provider.complete.call_args[1]["messages"][0].content \
        if provider.complete.call_args[1] else provider.complete.call_args[0][0][0].content
    # The question embedded in the prompt must not exceed 4000 chars
    assert len(long_question) > 4000
    assert "x" * 4001 not in called_content


@pytest.mark.asyncio
async def test_decompose_json_object_falls_back(tmp_wiki):
    """If the LLM returns a JSON object instead of an array, fall back to original question."""
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text='{"sub_questions": ["a", "b"]}', input_tokens=5, output_tokens=5
    )
    agent = QueryAgent(provider=provider, store=store, search=search)
    q = "What is AI?"
    result = await agent.decompose(q)
    assert result == [q]


@pytest.mark.asyncio
async def test_decompose_all_whitespace_after_filter_falls_back(tmp_wiki):
    """If all entries in the array are whitespace-only after filtering, fall back."""
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text='["   ", "\\t", ""]', input_tokens=5, output_tokens=5
    )
    agent = QueryAgent(provider=provider, store=store, search=search)
    q = "What is AI?"
    result = await agent.decompose(q)
    assert result == [q]


# ── performance: decompose() call count ──────────────────────────────────────

@pytest.mark.asyncio
async def test_decompose_called_exactly_once_per_query(tmp_wiki):
    """query() must call decompose() exactly once regardless of sub-question count."""
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = AsyncMock()
    provider.complete.side_effect = [
        CompletionResponse(text='["sub1", "sub2", "sub3"]',
                           input_tokens=10, output_tokens=10),
        CompletionResponse(text="answer", input_tokens=100, output_tokens=20),
    ]
    agent = QueryAgent(provider=provider, store=store, search=search,
                       gap_score_threshold=0.0)

    decompose_calls = []
    original_decompose = agent.decompose

    async def counting_decompose(q):
        decompose_calls.append(q)
        return await original_decompose(q)

    agent.decompose = counting_decompose
    await agent.query("multi-part question")
    assert len(decompose_calls) == 1


@pytest.mark.asyncio
async def test_gather_arity_matches_sub_question_count(tmp_wiki):
    """asyncio.gather() must receive exactly N coroutines for N sub-questions."""
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = AsyncMock()
    provider.complete.side_effect = [
        CompletionResponse(text='["q1", "q2", "q3"]',
                           input_tokens=10, output_tokens=10),
        CompletionResponse(text="answer", input_tokens=100, output_tokens=20),
    ]
    agent = QueryAgent(provider=provider, store=store, search=search,
                       gap_score_threshold=0.0)

    gather_arities: list[int] = []
    original_gather = asyncio.gather

    async def spy(*coros, **kw):
        gather_arities.append(len(coros))
        return await original_gather(*coros, **kw)

    import unittest.mock
    with unittest.mock.patch("synthadoc.agents.query_agent.asyncio.gather", spy):
        await agent.query("three-part question")

    assert gather_arities == [3]


@pytest.mark.asyncio
async def test_simple_question_uses_single_gather_coroutine(tmp_wiki):
    """A simple question decomposed to 1 sub-question must call gather with exactly 1 coroutine."""
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = AsyncMock()
    provider.complete.side_effect = [
        CompletionResponse(text='["What is AI?"]',
                           input_tokens=5, output_tokens=5),
        CompletionResponse(text="AI is ...", input_tokens=80, output_tokens=15),
    ]
    agent = QueryAgent(provider=provider, store=store, search=search,
                       gap_score_threshold=0.0)

    gather_arities: list[int] = []
    original_gather = asyncio.gather

    async def spy(*coros, **kw):
        gather_arities.append(len(coros))
        return await original_gather(*coros, **kw)

    import unittest.mock
    with unittest.mock.patch("synthadoc.agents.query_agent.asyncio.gather", spy):
        await agent.query("What is AI?")

    assert gather_arities == [1]


# ── cost field propagation ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_query_result_carries_input_and_output_tokens(tmp_wiki):
    """QueryResult must expose input_tokens and output_tokens from the answer LLM call."""
    store, search, provider = _make_agent(tmp_wiki)
    provider.complete.side_effect = [
        CompletionResponse(text='["term"]', input_tokens=10, output_tokens=5),
        CompletionResponse(text="The answer.", input_tokens=120, output_tokens=40),
    ]
    agent = QueryAgent(provider=provider, store=store, search=search,
                       gap_score_threshold=0.0)
    result = await agent.query("What is the answer?")
    assert result.input_tokens == 120
    assert result.output_tokens == 40
    assert result.tokens_used == 160  # 120 + 40


@pytest.mark.asyncio
async def test_query_result_input_output_tokens_nonzero_for_real_call(tmp_wiki):
    """input_tokens and output_tokens must be > 0 when the provider returns real counts."""
    store, search, provider = _make_agent(tmp_wiki)
    provider.complete.side_effect = [
        CompletionResponse(text='["sub"]', input_tokens=8, output_tokens=3),
        CompletionResponse(text="Answer here.", input_tokens=200, output_tokens=50),
    ]
    agent = QueryAgent(provider=provider, store=store, search=search,
                       gap_score_threshold=0.0)
    result = await agent.query("Any question?")
    assert result.input_tokens > 0
    assert result.output_tokens > 0


# ── knowledge gap detection ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_query_result_has_knowledge_gap_fields(tmp_wiki):
    """QueryResult must expose knowledge_gap and suggested_searches."""
    store, search, provider = _make_agent(tmp_wiki)
    agent = QueryAgent(provider=provider, store=store, search=search,
                       gap_score_threshold=0.0)
    result = await agent.query("What is AI?")
    assert hasattr(result, "knowledge_gap")
    assert hasattr(result, "suggested_searches")
    assert isinstance(result.suggested_searches, list)


@pytest.mark.asyncio
async def test_no_gap_when_pages_found_with_high_scores(tmp_wiki):
    """knowledge_gap must be False when enough pages with high BM25 scores are found."""
    from synthadoc.storage.wiki import WikiPage
    store = WikiStorage(tmp_wiki / "wiki")
    # Write 5 pages that will match the query well
    for i in range(5):
        store.write_page(f"ai-page-{i}", WikiPage(
            title=f"AI page {i}", tags=["ai"],
            content=f"Artificial intelligence machine learning deep learning neural network {i}.",
            status="active", confidence="high", sources=[],
        ))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = AsyncMock()
    provider.complete.side_effect = [
        CompletionResponse(text='["What is AI?"]', input_tokens=5, output_tokens=5),
        CompletionResponse(text="AI is...", input_tokens=100, output_tokens=20),
    ]
    agent = QueryAgent(provider=provider, store=store, search=search,
                       gap_score_threshold=0.0)  # disabled — never triggers
    result = await agent.query("What is artificial intelligence?")
    assert result.knowledge_gap is False
    assert result.suggested_searches == []


@pytest.mark.asyncio
async def test_gap_detected_when_empty_wiki(tmp_wiki):
    """knowledge_gap must be True when no pages are found (empty wiki)."""
    store, search, provider = _make_agent(tmp_wiki)
    provider.complete.side_effect = [
        CompletionResponse(text='["What is AI?"]', input_tokens=5, output_tokens=5),
        # SearchDecomposeAgent call for suggestions:
        CompletionResponse(text='["artificial intelligence overview", "machine learning basics"]',
                           input_tokens=8, output_tokens=8),
        # Answer synthesis call:
        CompletionResponse(text="No relevant pages found.", input_tokens=50, output_tokens=10),
    ]
    agent = QueryAgent(provider=provider, store=store, search=search)
    result = await agent.query("What is AI?")
    assert result.knowledge_gap is True
    assert len(result.suggested_searches) >= 1


@pytest.mark.asyncio
async def test_gap_detected_when_max_score_below_threshold(tmp_wiki):
    """knowledge_gap must be True when pages exist but max BM25 score is below threshold."""
    from synthadoc.storage.wiki import WikiPage
    store = WikiStorage(tmp_wiki / "wiki")
    # Write pages that are barely related (low BM25 score for the query)
    store.write_page("unrelated", WikiPage(
        title="Cooking Recipes", tags=["food"],
        content="How to bake bread. Mix flour and water.",
        status="active", confidence="high", sources=[],
    ))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = AsyncMock()
    provider.complete.side_effect = [
        CompletionResponse(text='["quantum computing"]', input_tokens=5, output_tokens=5),
        CompletionResponse(text='["quantum computing basics", "quantum gates explained"]',
                           input_tokens=8, output_tokens=8),
        CompletionResponse(text="I don't know.", input_tokens=50, output_tokens=10),
    ]
    # High threshold so even marginal matches trigger gap
    agent = QueryAgent(provider=provider, store=store, search=search,
                       gap_score_threshold=999.0)
    result = await agent.query("What is quantum computing?")
    assert result.knowledge_gap is True
    assert len(result.suggested_searches) >= 1


@pytest.mark.asyncio
async def test_gap_suggested_searches_come_from_search_decompose_agent(tmp_wiki):
    """suggested_searches must be the keyword strings from SearchDecomposeAgent.decompose()."""
    store, search, provider = _make_agent(tmp_wiki)
    provider.complete.side_effect = [
        CompletionResponse(text='["What is quantum computing?"]', input_tokens=5, output_tokens=5),
        CompletionResponse(text='["quantum computing basics", "qubit explained"]',
                           input_tokens=8, output_tokens=8),
        CompletionResponse(text="Answer.", input_tokens=50, output_tokens=10),
    ]
    agent = QueryAgent(provider=provider, store=store, search=search,
                       gap_score_threshold=999.0)
    result = await agent.query("What is quantum computing?")
    assert "quantum computing basics" in result.suggested_searches
    assert "qubit explained" in result.suggested_searches


@pytest.mark.asyncio
async def test_no_gap_search_decompose_not_called(tmp_wiki):
    """SearchDecomposeAgent must NOT be called when no gap is detected."""
    from synthadoc.storage.wiki import WikiPage
    store = WikiStorage(tmp_wiki / "wiki")
    for i in range(5):
        store.write_page(f"page-{i}", WikiPage(
            title=f"Page {i}", tags=["ai"],
            content=f"Artificial intelligence AI machine learning {i}.",
            status="active", confidence="high", sources=[],
        ))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = AsyncMock()
    provider.complete.side_effect = [
        CompletionResponse(text='["What is AI?"]', input_tokens=5, output_tokens=5),
        CompletionResponse(text="AI is...", input_tokens=100, output_tokens=20),
    ]
    agent = QueryAgent(provider=provider, store=store, search=search,
                       gap_score_threshold=0.0)  # never triggers
    result = await agent.query("What is AI?")
    # Only 2 provider calls: decompose + answer. No SearchDecomposeAgent call.
    assert provider.complete.call_count == 2
    assert result.knowledge_gap is False


@pytest.mark.asyncio
async def test_gap_detected_when_pages_are_off_topic(tmp_wiki):
    """Signal 3: gap triggers when retrieved pages share vocabulary but lack key content words.

    This covers the real-world case where a gardening wiki returns spring-flower
    pages for a vegetables query — BM25 scores are high (shared: spring, Canada,
    planting) but none of the pages actually contain the word 'vegetable'.
    """
    from synthadoc.storage.wiki import WikiPage
    store = WikiStorage(tmp_wiki / "wiki")
    # Write 5 pages that share gardening vocabulary but say nothing about vegetables.
    for i in range(5):
        store.write_page(f"flower-page-{i}", WikiPage(
            title=f"Spring Flowers {i}", tags=["flowers"],
            content=(
                "Spring planting in Canada. Best flowers for Canadian gardens. "
                "Plant tulips and daffodils after the last frost date in spring. "
                "Soil preparation for flower beds in Canadian climate zones."
            ),
            status="active", confidence="high", sources=[],
        ))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = AsyncMock()
    provider.complete.side_effect = [
        # decompose call — single sub-question
        CompletionResponse(text='["What vegetables grow in Canadian spring?"]',
                           input_tokens=5, output_tokens=5),
        # SearchDecomposeAgent call for suggestions (gap triggered)
        CompletionResponse(text='["canadian spring vegetables planting", "frost dates vegetable Canada"]',
                           input_tokens=8, output_tokens=8),
        # answer synthesis call
        CompletionResponse(text="No vegetable info found.", input_tokens=80, output_tokens=15),
    ]
    # Threshold high enough that signal 2 alone would not trigger (flowers pages will
    # score well on BM25 for this query due to shared vocabulary).
    agent = QueryAgent(provider=provider, store=store, search=search,
                       gap_score_threshold=0.01)   # signal 2 disabled; signal 3 must fire
    result = await agent.query("What vegetables grow well in a Canadian spring?")
    # Signal 3: none of the flower pages contain 'vegetabl' — gap must be detected.
    assert result.knowledge_gap is True
    assert len(result.suggested_searches) >= 1


def _fake_results(slugs: list[str], score: float = 5.0) -> list[SearchResult]:
    """Return mock SearchResult list for patching bm25_search."""
    return [SearchResult(slug=s, score=score, title=s, snippet="") for s in slugs]


@pytest.mark.asyncio
async def test_no_gap_when_one_key_term_is_a_synonym(tmp_wiki):
    """Signal 3 must not fire when the rarest key term is absent only because the
    wiki uses a different word for the same concept (synonym/location variant).

    Real-world regression: query uses 'backyard' but wiki pages say 'garden'.
    'backyard' has zero doc-frequency; the fix is to skip it and use the rarest
    *covered* term ('plant') as the discriminator instead.

    bm25_search is mocked so BM25 IDF behaviour does not affect this test.
    """
    store = WikiStorage(tmp_wiki / "wiki")
    # Pages cover the topic well using "garden" throughout — "backyard" never appears.
    # "plant" appears ≥ 3 times per page (as substring of "plants"/"Plant").
    slugs = [f"garden-page-{i}" for i in range(5)]
    for slug in slugs:
        store.write_page(slug, WikiPage(
            title="Garden Plants", tags=["garden"],
            content=(
                "Best plants for Canadian gardens. "
                "Garden plants for partial shade areas. "
                "Plant selection for shaded garden beds. "
                "Shade-tolerant garden plants for your yard."
            ),
            status="active", confidence="high", sources=[],
        ))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = AsyncMock()
    provider.complete.side_effect = [
        CompletionResponse(text='["What plants grow well in a backyard?"]',
                           input_tokens=5, output_tokens=5),
        CompletionResponse(text="Many plants grow well in Canadian gardens.",
                           input_tokens=80, output_tokens=20),
    ]
    agent = QueryAgent(provider=provider, store=store, search=search,
                       gap_score_threshold=0.01)  # signal 2 disabled; only signal 3 can fire
    with patch.object(agent._search, "bm25_search", return_value=_fake_results(slugs)):
        result = await agent.query("What plants grow well in a backyard?")
    # "backyard" is absent (wiki says "garden"), so it is skipped as a zero-freq term.
    # "plant" covers all 5 pages with freq ≥ 3 → signal 3 does not fire.
    assert result.knowledge_gap is False
    assert result.suggested_searches == []


@pytest.mark.asyncio
async def test_gap_signal3_boundary_exactly_two_on_topic_pages(tmp_wiki):
    """Signal 3 must NOT trigger when exactly two retrieved pages cover the
    discriminating term with sufficient frequency.

    The threshold is _pages_with_overlap < 2, so exactly 2 pages = no gap.

    bm25_search is mocked so BM25 IDF behaviour does not affect this test.
    """
    store = WikiStorage(tmp_wiki / "wiki")
    # 2 orchid pages have "orchid" ≥ 3 times; 3 pages have none.
    for i in range(2):
        store.write_page(f"orchid-page-{i}", WikiPage(
            title="Orchid Care", tags=["orchid"],
            content=(
                "Orchid growing tips for home. "
                "The best orchid varieties for shade. "
                "Orchid plants need indirect light."
            ),
            status="active", confidence="high", sources=[],
        ))
    for i in range(3):
        store.write_page(f"generic-page-{i}", WikiPage(
            title="Garden Tips", tags=["garden"],
            content="Best plants for Canadian gardens. Garden design tips.",
            status="active", confidence="high", sources=[],
        ))
    all_slugs = [f"orchid-page-{i}" for i in range(2)] + [f"generic-page-{i}" for i in range(3)]
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = AsyncMock()
    provider.complete.side_effect = [
        CompletionResponse(text='["What orchid plants grow well?"]',
                           input_tokens=5, output_tokens=5),
        CompletionResponse(text="Orchid answer.", input_tokens=80, output_tokens=15),
    ]
    agent = QueryAgent(provider=provider, store=store, search=search,
                       gap_score_threshold=0.01)
    with patch.object(agent._search, "bm25_search", return_value=_fake_results(all_slugs)):
        result = await agent.query("What orchid plants grow well indoors?")
    # "orchid" is the discriminating term (rarest covered, doc_freq=2).
    # Exactly 2 pages have "orchid" ≥ 3 times; 2 < 2 is False → no gap.
    assert result.knowledge_gap is False
    assert result.suggested_searches == []


@pytest.mark.asyncio
async def test_gap_signal3_boundary_one_on_topic_page(tmp_wiki):
    """Signal 3 DOES trigger when only one retrieved page covers the discriminating
    term with sufficient frequency (1 < 2 → gap).

    bm25_search is mocked so BM25 IDF behaviour does not affect this test.
    """
    store = WikiStorage(tmp_wiki / "wiki")
    # Only 1 page has "orchid" ≥ 3 times; 4 pages are off-topic.
    store.write_page("orchid-page", WikiPage(
        title="Orchid Care", tags=["orchid"],
        content=(
            "Orchid growing tips for home. "
            "The best orchid varieties for shade. "
            "Orchid plants need indirect light."
        ),
        status="active", confidence="high", sources=[],
    ))
    for i in range(4):
        store.write_page(f"generic-page-{i}", WikiPage(
            title="Garden Tips", tags=["garden"],
            content="Best plants for Canadian gardens. Garden design tips.",
            status="active", confidence="high", sources=[],
        ))
    all_slugs = ["orchid-page"] + [f"generic-page-{i}" for i in range(4)]
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = AsyncMock()
    provider.complete.side_effect = [
        CompletionResponse(text='["What orchid plants grow well?"]',
                           input_tokens=5, output_tokens=5),
        CompletionResponse(text='["orchid care guide", "indoor orchid growing"]',
                           input_tokens=8, output_tokens=8),
        CompletionResponse(text="Limited orchid info.", input_tokens=80, output_tokens=15),
    ]
    agent = QueryAgent(provider=provider, store=store, search=search,
                       gap_score_threshold=0.01)
    with patch.object(agent._search, "bm25_search", return_value=_fake_results(all_slugs)):
        result = await agent.query("What orchid plants grow well indoors?")
    # "orchid" is the discriminating term; only 1 page has it ≥ 2 times → 1 < 2 → gap.
    assert result.knowledge_gap is True
    assert len(result.suggested_searches) >= 1


@pytest.mark.asyncio
async def test_no_gap_multi_aspect_query_with_generic_corpus_term(tmp_wiki):
    """Signal 3 must not fire for a multi-aspect query when the wiki covers the topic
    well but the corpus-dominant term ('shade') is filtered as hyper-generic.

    Real-world regression: query asks about 'full sun, partial shade, and full shade'.
    The wiki has many shade pages.  'shade' and 'plant' appear in every page (>60%
    coverage) so they are filtered as generic.  'partial' is the rarest specific term.
    Pages that mention 'partial' at least twice count as on-topic — if ≥ 2 pages pass,
    no gap fires even though 'shade' was excluded from the specific-term check.

    bm25_search is mocked to return the shade pages directly.
    """
    store = WikiStorage(tmp_wiki / "wiki")
    # 4 pages cover partial shade explicitly; 2 are full-shade only.
    for i in range(4):
        store.write_page(f"partial-shade-{i}", WikiPage(
            title=f"Partial Shade Plants {i}", tags=["shade"],
            content=(
                "Best plants for partial shade in Canadian gardens. "
                "Partial shade perennials thrive under dappled light. "
                "These shade-tolerant plants suit partial shade conditions. "
                "Plant selection for partial shade and full shade areas."
            ),
            status="active", confidence="high", sources=[],
        ))
    for i in range(2):
        store.write_page(f"full-shade-{i}", WikiPage(
            title=f"Full Shade Plants {i}", tags=["shade"],
            content=(
                "Best plants for full shade. Hostas thrive in shade. "
                "Shade plants for Canadian gardens. Deep shade perennials."
            ),
            status="active", confidence="high", sources=[],
        ))
    all_slugs = [f"partial-shade-{i}" for i in range(4)] + [f"full-shade-{i}" for i in range(2)]
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = AsyncMock()
    provider.complete.side_effect = [
        CompletionResponse(text='["best plants for full sun partial shade and full shade Canada"]',
                           input_tokens=5, output_tokens=5),
        CompletionResponse(text="Here are plants for each light level...",
                           input_tokens=200, output_tokens=60),
    ]
    agent = QueryAgent(provider=provider, store=store, search=search,
                       gap_score_threshold=0.01)  # signal 2 disabled; only signal 3 can fire
    with patch.object(agent._search, "bm25_search", return_value=_fake_results(all_slugs)):
        result = await agent.query(
            "What are the best plants for full sun, partial shade, and full shade in a Canadian backyard?"
        )
    # 4 pages mention "partial" ≥ 2 times → on_topic_pages = 4 ≥ 2 → no gap.
    assert result.knowledge_gap is False
    assert result.suggested_searches == []


@pytest.mark.asyncio
async def test_gap_signal5_defining_term_barely_present(tmp_wiki):
    """Signal 5: gap triggers when at least one specific key term never appears ≥ 2
    times in any single candidate page, even though it exists in the wiki (freq > 0
    across pages) so signal 4 does not fire.

    Real-world case: "quantum error correction" in a history-of-computing wiki.
    "quantum" is present in 2 candidate pages but only once per page (passing mention).
    "error" and "correction" each appear ≥ 2 times in dedicated Bombe pages.

    Signal breakdown for this test:
    - Signal 1: 8 candidates ≥ 3 → no fire
    - Signal 2: gap_score_threshold=0.01 → no fire
    - Signal 3: 2 pages have error/correction ≥ 2 → on_topic_pages=2 ≥ 2 → no fire
    - Signal 4: all 3 terms have doc_freq > 0 → no zero-freq → no fire
    - Signal 5: quantum_qualifying_pages=0 (never ≥ 2 in any page) →
                min(quantum=0, error=2, correction=2)=0 → gap=True ✓

    bm25_search is mocked so BM25 IDF behaviour does not affect this test.
    """
    store = WikiStorage(tmp_wiki / "wiki")

    # 2 pages where "error" and "correction" appear ≥ 2 times (Bombe incidental matches).
    for i in range(2):
        store.write_page(f"bombe-page-{i}", WikiPage(
            title=f"The Bombe Machine {i}", tags=["history"],
            content=(
                "The Bombe detected incorrect Enigma settings by finding contradictions. "
                "Each error in the assumed settings triggered a correction cycle. "
                "The machine applied error correction logic to narrow down Enigma keys. "
                "Finding an error led to rejecting that key and applying a correction."
            ),
            status="active", confidence="high", sources=[],
        ))
    # 2 pages that each mention "quantum" exactly once — present but not covered.
    for i in range(2):
        store.write_page(f"quantum-mention-{i}", WikiPage(
            title=f"Computing Frontiers {i}", tags=["history"],
            content=(
                "Transistors replaced vacuum tubes in the 1950s, paving the way for "
                "integrated circuits. Researchers have since explored quantum computing "
                "as the next frontier, but this wiki does not yet cover that topic."
            ),
            status="active", confidence="high", sources=[],
        ))
    # 4 filler pages with none of the key terms.
    for i in range(4):
        store.write_page(f"other-page-{i}", WikiPage(
            title=f"Computing History {i}", tags=["history"],
            content=(
                "Alan Turing proposed the Turing machine as a theoretical model of computation. "
                "John von Neumann designed the stored-program architecture."
            ),
            status="active", confidence="high", sources=[],
        ))

    all_slugs = (
        [f"bombe-page-{i}" for i in range(2)]
        + [f"quantum-mention-{i}" for i in range(2)]
        + [f"other-page-{i}" for i in range(4)]
    )
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    provider = AsyncMock()
    provider.complete.side_effect = [
        CompletionResponse(text='["What is quantum error correction?"]',
                           input_tokens=5, output_tokens=5),
        # SearchDecomposeAgent call for suggestions (gap triggered):
        CompletionResponse(text='["quantum error correction explained", "qubit error rates"]',
                           input_tokens=8, output_tokens=8),
        CompletionResponse(text="No quantum info found.", input_tokens=80, output_tokens=15),
    ]
    agent = QueryAgent(provider=provider, store=store, search=search,
                       gap_score_threshold=0.01)  # signal 2 disabled
    with patch.object(agent._search, "bm25_search", return_value=_fake_results(all_slugs)):
        result = await agent.query("What is quantum error correction?")
    # "quantum" never appears ≥ 2 times in any candidate → min_qualifying=0 → signal 5.
    assert result.knowledge_gap is True
    assert len(result.suggested_searches) >= 1
