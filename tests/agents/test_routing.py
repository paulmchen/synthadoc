# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
from unittest.mock import AsyncMock

from synthadoc.agents._routing import pick_routing_branches
from synthadoc.providers.base import CompletionResponse

_BRANCHES = {"People": ["alan-turing"], "Hardware": ["eniac"]}


@pytest.mark.asyncio
async def test_empty_branches_returns_empty_no_llm_call():
    provider = AsyncMock()
    result = await pick_routing_branches(provider, {}, "context", multi=True)
    assert result == []
    provider.complete.assert_not_called()


@pytest.mark.asyncio
async def test_multi_valid_json_response():
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text='["People"]', input_tokens=10, output_tokens=5
    )
    result = await pick_routing_branches(provider, _BRANCHES, "context", multi=True)
    assert result == ["People"]


@pytest.mark.asyncio
async def test_multi_filters_unknown_branches():
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text='["People", "Unknown"]', input_tokens=10, output_tokens=5
    )
    result = await pick_routing_branches(provider, _BRANCHES, "context", multi=True)
    assert result == ["People"]


@pytest.mark.asyncio
async def test_multi_no_json_array_in_response_returns_empty():
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text="People", input_tokens=10, output_tokens=5
    )
    result = await pick_routing_branches(provider, _BRANCHES, "context", multi=True)
    assert result == []


@pytest.mark.asyncio
async def test_multi_invalid_json_returns_empty():
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text="[invalid", input_tokens=10, output_tokens=5
    )
    result = await pick_routing_branches(provider, _BRANCHES, "context", multi=True)
    assert result == []


@pytest.mark.asyncio
async def test_llm_exception_returns_empty():
    provider = AsyncMock()
    provider.complete.side_effect = RuntimeError("network error")
    result = await pick_routing_branches(provider, _BRANCHES, "context", multi=False)
    assert result == []


@pytest.mark.asyncio
async def test_single_unknown_response_falls_back_to_first_branch():
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text="NonExistentBranch", input_tokens=10, output_tokens=5
    )
    result = await pick_routing_branches(provider, _BRANCHES, "context", multi=False)
    assert result == [next(iter(_BRANCHES))]


@pytest.mark.asyncio
async def test_multi_empty_array_response():
    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text="[]", input_tokens=10, output_tokens=5
    )
    result = await pick_routing_branches(provider, _BRANCHES, "context", multi=True)
    assert result == []
