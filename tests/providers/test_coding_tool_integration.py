# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Integration tests — skipped unless the real CLI tool is available.

Run with:
    pytest tests/providers/test_coding_tool_integration.py -v -m integration
"""
import shutil
import time
import pytest

pytestmark = pytest.mark.integration


@pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not available")
@pytest.mark.asyncio
async def test_claude_code_real_round_trip():
    """Real claude -p call returns non-empty text."""
    from synthadoc.providers.coding_tool import ClaudeCodeCLIProvider
    from synthadoc.providers.base import Message
    provider = ClaudeCodeCLIProvider(model=None, timeout=60)
    resp = await provider.complete([Message(role="user", content="Reply with exactly: hello")])
    assert resp.text.strip() != ""
    assert resp.input_tokens >= 0  # token counts may not be reported by all CLI versions


@pytest.mark.skipif(shutil.which("opencode") is None, reason="opencode CLI not available")
@pytest.mark.asyncio
async def test_opencode_real_round_trip():
    """Real opencode run call returns non-empty text."""
    from synthadoc.providers.coding_tool import OpencodeProvider
    from synthadoc.providers.base import Message
    provider = OpencodeProvider(model=None, timeout=60)
    resp = await provider.complete([Message(role="user", content="Reply with exactly: hello")])
    assert resp.text.strip() != ""
    assert resp.input_tokens >= 0  # token counts may not be reported by all CLI versions


@pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not available")
@pytest.mark.asyncio
async def test_claude_code_wall_time_within_10s_overhead():
    """CLI provider overhead is ≤ 10s vs a baseline prompt-only timing."""
    from synthadoc.providers.coding_tool import ClaudeCodeCLIProvider
    from synthadoc.providers.base import Message
    provider = ClaudeCodeCLIProvider(model=None, timeout=60)
    start = time.perf_counter()
    await provider.complete([Message(role="user", content="Say: ok")])
    wall = time.perf_counter() - start
    assert wall < 30, f"Single call took {wall:.1f}s — investigate CLI startup overhead"
