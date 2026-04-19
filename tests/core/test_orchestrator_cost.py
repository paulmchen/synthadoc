# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Tests that estimate_cost() is wired correctly through Orchestrator.query()
and Orchestrator._run_ingest() — verifying the cost flows from token counts
to the queue result, not just that the pricing function works in isolation."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from synthadoc.core.orchestrator import Orchestrator
from synthadoc.config import Config, AgentsConfig, AgentConfig
from synthadoc.agents.query_agent import QueryResult
from synthadoc.agents.ingest_agent import IngestResult


def _cfg(provider: str = "anthropic", model: str = "claude-haiku-4-5-20251001") -> Config:
    return Config(agents=AgentsConfig(default=AgentConfig(provider=provider, model=model)))


def _mock_query_agent(input_tokens: int, output_tokens: int, answer: str = "ok"):
    mock_agent = MagicMock()
    mock_agent.query = AsyncMock(return_value=QueryResult(
        question="q",
        answer=answer,
        citations=[],
        tokens_used=input_tokens + output_tokens,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    ))
    return mock_agent


def _mock_ingest_agent(input_tokens: int, output_tokens: int):
    mock_agent = MagicMock()
    mock_agent.ingest = AsyncMock(return_value=IngestResult(
        source="test.md",
        pages_created=["page-a"],
        tokens_used=input_tokens + output_tokens,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=0.0,  # orchestrator must overwrite this
    ))
    return mock_agent


# ── Orchestrator.query() cost ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_orchestrator_query_records_nonzero_cost_for_known_model(tmp_wiki):
    """Orchestrator.query() must record a non-zero cost_usd for a known paid model."""
    cfg = _cfg("anthropic", "claude-haiku-4-5-20251001")
    orch = Orchestrator(wiki_root=tmp_wiki, config=cfg)
    await orch.init()

    mock_agent = _mock_query_agent(input_tokens=1000, output_tokens=500)
    recorded: dict = {}

    async def capture_record_query(**kwargs):
        recorded.update(kwargs)

    with patch("synthadoc.agents.query_agent.QueryAgent", return_value=mock_agent), \
         patch("synthadoc.core.orchestrator.make_provider", return_value=MagicMock(spec=[])), \
         patch.object(orch._audit, "record_query", side_effect=capture_record_query), \
         patch.object(orch._log, "log_query"):
        await orch.query("test question")

    assert "cost_usd" in recorded
    assert recorded["cost_usd"] > 0.0, "Known paid model must produce non-zero cost"


@pytest.mark.asyncio
async def test_orchestrator_query_records_zero_cost_for_ollama(tmp_wiki):
    """Orchestrator.query() must record cost_usd=0.0 when provider is Ollama."""
    from synthadoc.providers.ollama import OllamaProvider
    cfg = _cfg("ollama", "llama3")
    orch = Orchestrator(wiki_root=tmp_wiki, config=cfg)
    await orch.init()

    mock_agent = _mock_query_agent(input_tokens=1000, output_tokens=500)
    recorded: dict = {}

    async def capture_record_query(**kwargs):
        recorded.update(kwargs)

    mock_ollama_provider = MagicMock(spec=OllamaProvider)

    with patch("synthadoc.agents.query_agent.QueryAgent", return_value=mock_agent), \
         patch("synthadoc.core.orchestrator.make_provider", return_value=mock_ollama_provider), \
         patch.object(orch._audit, "record_query", side_effect=capture_record_query), \
         patch.object(orch._log, "log_query"):
        await orch.query("test question")

    assert recorded["cost_usd"] == 0.0, "Ollama (local) must always record $0.00"


@pytest.mark.asyncio
async def test_orchestrator_query_cost_scales_with_token_count(tmp_wiki):
    """Doubling the token count must double the recorded cost."""
    cfg = _cfg("anthropic", "claude-haiku-4-5-20251001")
    orch = Orchestrator(wiki_root=tmp_wiki, config=cfg)
    await orch.init()

    costs = []

    for multiplier in (1, 2):
        mock_agent = _mock_query_agent(
            input_tokens=1000 * multiplier,
            output_tokens=500 * multiplier,
        )
        recorded: dict = {}

        async def capture(**kwargs):
            recorded.update(kwargs)

        with patch("synthadoc.agents.query_agent.QueryAgent", return_value=mock_agent), \
             patch("synthadoc.core.orchestrator.make_provider", return_value=MagicMock(spec=[])), \
             patch.object(orch._audit, "record_query", side_effect=capture), \
             patch.object(orch._log, "log_query"):
            await orch.query("test question")

        costs.append(recorded["cost_usd"])

    assert abs(costs[1] - 2 * costs[0]) < 1e-9, "Cost must scale linearly with token count"


# ── Orchestrator._run_ingest() cost ──────────────────────────────────────────
# _run_ingest() passes cost_usd to queue.complete(result={..., "cost_usd": ...}).
# We spy on queue.complete to assert the correct cost reaches it.

async def _run_and_capture_ingest_cost(orch, input_tokens: int, output_tokens: int) -> float:
    """Run _run_ingest with a mock agent and return the cost_usd passed to queue.complete."""
    mock_agent = _mock_ingest_agent(input_tokens=input_tokens, output_tokens=output_tokens)
    job_id = await orch._queue.enqueue("ingest", {"source": "test.md", "force": False})

    captured: dict = {}
    original_complete = orch._queue.complete

    async def spy_complete(jid, result=None):
        if result:
            captured.update(result)
        await original_complete(jid, result=result)

    with patch("synthadoc.core.orchestrator.make_provider", return_value=MagicMock(spec=[])), \
         patch("synthadoc.agents.ingest_agent.IngestAgent", return_value=mock_agent), \
         patch.object(orch._queue, "complete", side_effect=spy_complete):
        await orch._run_ingest(job_id, "test.md", auto_confirm=True)

    return captured.get("cost_usd", None)


@pytest.mark.asyncio
async def test_orchestrator_ingest_sets_nonzero_cost_for_known_model(tmp_wiki):
    """_run_ingest() must pass cost_usd > 0 to queue.complete() for a paid model."""
    cfg = _cfg("anthropic", "claude-haiku-4-5-20251001")
    orch = Orchestrator(wiki_root=tmp_wiki, config=cfg)
    await orch.init()
    cost = await _run_and_capture_ingest_cost(orch, input_tokens=1000, output_tokens=500)
    assert cost is not None, "queue.complete() must be called with cost_usd"
    assert cost > 0.0, "Known paid model must produce non-zero ingest cost"


@pytest.mark.asyncio
async def test_orchestrator_ingest_sets_zero_cost_for_ollama(tmp_wiki):
    """_run_ingest() must pass cost_usd=0.0 to queue.complete() for Ollama."""
    cfg = _cfg("ollama", "llama3")
    orch = Orchestrator(wiki_root=tmp_wiki, config=cfg)
    await orch.init()
    cost = await _run_and_capture_ingest_cost(orch, input_tokens=1000, output_tokens=500)
    assert cost == 0.0, "Ollama must record $0.00 ingest cost"


@pytest.mark.asyncio
async def test_orchestrator_ingest_unknown_model_uses_fallback_nonzero(tmp_wiki):
    """Unknown model must use the conservative fallback rate, not silently report $0."""
    cfg = _cfg("openai", "some-future-model-not-in-table")
    orch = Orchestrator(wiki_root=tmp_wiki, config=cfg)
    await orch.init()
    cost = await _run_and_capture_ingest_cost(orch, input_tokens=1000, output_tokens=500)
    assert cost is not None
    assert cost > 0.0, "Unknown model must use fallback rate, not $0.00"
