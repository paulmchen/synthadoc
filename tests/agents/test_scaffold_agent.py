# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import json
import pytest
from unittest.mock import AsyncMock
from synthadoc.agents.scaffold_agent import ScaffoldAgent, ScaffoldResult
from synthadoc.providers.base import CompletionResponse, Message


def _make_provider(json_payload: dict) -> AsyncMock:
    """Return a mock provider that returns the given dict as JSON text."""
    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=CompletionResponse(
        text=json.dumps(json_payload),
        input_tokens=100,
        output_tokens=200,
    ))
    return provider


_VALID_RESPONSE = {
    "categories": [
        {"heading": "Key Concepts", "description": "Fundamental ideas in the domain"},
        {"heading": "People", "description": "Notable figures"},
    ],
    "agents_guidelines": "Summarize claims. Use [[wikilinks]].",
    "purpose_include": "Topics directly related to Machine Learning.",
    "purpose_exclude": "Unrelated domains such as cooking.",
    "dashboard_intro": "A wiki tracking Machine Learning knowledge.",
}


@pytest.mark.asyncio
async def test_scaffold_returns_result():
    """ScaffoldAgent.scaffold() returns a ScaffoldResult with all fields populated."""
    provider = _make_provider(_VALID_RESPONSE)
    agent = ScaffoldAgent(provider=provider)
    result = await agent.scaffold(domain="Machine Learning")
    assert isinstance(result, ScaffoldResult)
    assert "Key Concepts" in result.index_md
    assert "People" in result.index_md
    assert "Machine Learning" in result.agents_md
    assert "Machine Learning" in result.purpose_md
    assert "Machine Learning" in result.dashboard_intro


@pytest.mark.asyncio
async def test_scaffold_index_md_has_frontmatter():
    """index.md must include YAML frontmatter."""
    provider = _make_provider(_VALID_RESPONSE)
    agent = ScaffoldAgent(provider=provider)
    result = await agent.scaffold(domain="Machine Learning")
    assert result.index_md.startswith("---")
    assert "title: Index" in result.index_md


@pytest.mark.asyncio
async def test_scaffold_protected_slugs_appear_in_prompt():
    """Protected slugs must be included in the LLM prompt."""
    provider = _make_provider(_VALID_RESPONSE)
    agent = ScaffoldAgent(provider=provider)
    await agent.scaffold(domain="ML", protected_slugs=["neural-networks", "transformers"])
    call_kwargs = provider.complete.call_args.kwargs
    call_messages = call_kwargs.get("messages") or provider.complete.call_args[0][0]
    prompt_text = " ".join(m.content for m in call_messages)
    assert "neural-networks" in prompt_text
    assert "transformers" in prompt_text


@pytest.mark.asyncio
async def test_scaffold_handles_json_with_markdown_fences():
    """Parser must strip ```json fences if the LLM wraps the response."""
    fenced = f"```json\n{json.dumps(_VALID_RESPONSE)}\n```"
    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=CompletionResponse(
        text=fenced, input_tokens=10, output_tokens=20
    ))
    agent = ScaffoldAgent(provider=provider)
    result = await agent.scaffold(domain="ML")
    assert "Key Concepts" in result.index_md


@pytest.mark.asyncio
async def test_scaffold_raises_on_invalid_json():
    """ScaffoldAgent must raise ValueError if the LLM returns unparseable text."""
    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=CompletionResponse(
        text="not json at all", input_tokens=10, output_tokens=5
    ))
    agent = ScaffoldAgent(provider=provider)
    with pytest.raises(ValueError, match="scaffold"):
        await agent.scaffold(domain="ML")
