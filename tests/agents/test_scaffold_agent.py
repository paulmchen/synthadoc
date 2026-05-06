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
        {"heading": "Key Concepts", "description": "Fundamental ideas in the domain", "slugs": ["neural-networks", "backpropagation"]},
        {"heading": "People", "description": "Notable figures", "slugs": []},
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
async def test_scaffold_index_md_has_wikilinks():
    """index.md must include [[slug]] wikilinks for slugs returned by the LLM."""
    provider = _make_provider(_VALID_RESPONSE)
    agent = ScaffoldAgent(provider=provider)
    result = await agent.scaffold(domain="Machine Learning")
    assert "- [[neural-networks]]" in result.index_md
    assert "- [[backpropagation]]" in result.index_md


@pytest.mark.asyncio
async def test_scaffold_protected_slugs_instruction_in_prompt():
    """Protected slugs must trigger assignment instruction in the LLM prompt."""
    provider = _make_provider(_VALID_RESPONSE)
    agent = ScaffoldAgent(provider=provider)
    await agent.scaffold(domain="ML", protected_slugs=["neural-networks", "transformers"])
    call_kwargs = provider.complete.call_args.kwargs
    call_messages = call_kwargs.get("messages") or provider.complete.call_args[0][0]
    prompt_text = " ".join(m.content for m in call_messages)
    assert "every protected slug must appear in exactly one category" in prompt_text.lower()


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


# ── CJK (Chinese / Japanese / Korean) coverage ───────────────────────────────

_CJK_VALID_RESPONSE = {
    "categories": [
        {"heading": "核心概念", "description": "人工智能的基本原理", "slugs": ["神经网络", "机器学习"]},
        {"heading": "应用领域", "description": "实际应用场景", "slugs": ["自然语言处理"]},
    ],
    "agents_guidelines": "总结关键主张。使用[[维基链接]]交叉引用相关页面。",
    "purpose_include": "与人工智能直接相关的主题。",
    "purpose_exclude": "与人工智能无关的领域，例如烹饪。",
    "dashboard_intro": "跟踪人工智能知识库领域知识的维基百科。",
}


@pytest.mark.asyncio
async def test_scaffold_cjk_domain_name_in_all_outputs():
    """Scaffold with a CJK domain name → all output documents contain the CJK domain string."""
    provider = _make_provider(_CJK_VALID_RESPONSE)
    agent = ScaffoldAgent(provider=provider)
    result = await agent.scaffold(domain="人工智能知识库")

    assert isinstance(result, ScaffoldResult)
    assert "人工智能知识库" in result.agents_md
    assert "人工智能知识库" in result.purpose_md
    assert "人工智能知识库" in result.dashboard_intro


@pytest.mark.asyncio
async def test_scaffold_cjk_categories_produce_wikilinks():
    """LLM returns CJK category headings and CJK slugs → index.md contains CJK [[wikilinks]]."""
    provider = _make_provider(_CJK_VALID_RESPONSE)
    agent = ScaffoldAgent(provider=provider)
    result = await agent.scaffold(domain="人工智能知识库")

    assert "核心概念" in result.index_md
    assert "应用领域" in result.index_md
    assert "- [[神经网络]]" in result.index_md
    assert "- [[机器学习]]" in result.index_md
    assert "- [[自然语言处理]]" in result.index_md


# ── Protected scaffold zone ───────────────────────────────────────────────────

def test_scaffold_preserves_user_content_above_marker():
    from synthadoc.agents.scaffold_agent import SCAFFOLD_MARKER, preserve_user_zone

    existing = "My custom intro.\n\n<!-- synthadoc:scaffold -->\n\n## Old Section\n- [[old]]\n"
    new_scaffold = "## People\n- [[alan-turing]]\n"
    result = preserve_user_zone(existing, new_scaffold)
    assert "My custom intro." in result
    assert "## People" in result
    assert "## Old Section" not in result
    assert SCAFFOLD_MARKER in result


def test_scaffold_no_marker_returns_new_content():
    from synthadoc.agents.scaffold_agent import preserve_user_zone
    result = preserve_user_zone("", "## People\n- [[alan-turing]]\n")
    assert result == "## People\n- [[alan-turing]]\n"


def test_scaffold_marker_without_user_zone():
    from synthadoc.agents.scaffold_agent import SCAFFOLD_MARKER, preserve_user_zone
    existing = f"{SCAFFOLD_MARKER}\n\n## Old Section\n"
    new_scaffold = "## New Section\n"
    result = preserve_user_zone(existing, new_scaffold)
    assert SCAFFOLD_MARKER in result
    assert "## New Section" in result
    assert "## Old Section" not in result
