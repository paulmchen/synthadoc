# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import asyncio
import pytest
from unittest.mock import patch, AsyncMock, MagicMock


def _make_mock_proc(stdout: bytes, stderr: bytes, returncode: int):
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.kill = MagicMock()
    return proc


@pytest.mark.asyncio
async def test_base_raises_environment_error_when_binary_missing():
    """Binary not in PATH → EnvironmentError at construction."""
    with patch("shutil.which", return_value=None):
        from synthadoc.providers.coding_tool import ClaudeCodeCLIProvider
        with pytest.raises(EnvironmentError, match="claude"):
            ClaudeCodeCLIProvider(model=None, timeout=30)


@pytest.mark.asyncio
async def test_base_raises_timeout_error():
    """asyncio.TimeoutError from communicate → TimeoutError."""
    with patch("shutil.which", return_value="/usr/bin/claude"):
        from synthadoc.providers.coding_tool import ClaudeCodeCLIProvider
        provider = ClaudeCodeCLIProvider(model=None, timeout=1)

    mock_proc = MagicMock()
    mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
    mock_proc.kill = MagicMock()

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        from synthadoc.providers.base import Message
        with pytest.raises(TimeoutError, match="timed out"):
            await provider.complete([Message(role="user", content="hello")])


@pytest.mark.asyncio
async def test_base_raises_runtime_error_on_nonzero_exit():
    """Non-zero exit code → RuntimeError with stderr."""
    with patch("shutil.which", return_value="/usr/bin/claude"):
        from synthadoc.providers.coding_tool import ClaudeCodeCLIProvider
        provider = ClaudeCodeCLIProvider(model=None, timeout=30)

    mock_proc = _make_mock_proc(b"", b"something went wrong", returncode=1)
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        from synthadoc.providers.base import Message
        with pytest.raises(RuntimeError, match="something went wrong"):
            await provider.complete([Message(role="user", content="hello")])


@pytest.mark.asyncio
async def test_base_raises_quota_exhausted():
    """Quota exhaustion pattern in stderr → CodingToolQuotaExhaustedException."""
    with patch("shutil.which", return_value="/usr/bin/claude"):
        from synthadoc.providers.coding_tool import ClaudeCodeCLIProvider
        provider = ClaudeCodeCLIProvider(model=None, timeout=30)

    mock_proc = _make_mock_proc(b"", b"Claude AI usage limit reached", returncode=1)
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        from synthadoc.providers.base import Message
        from synthadoc.errors import CodingToolQuotaExhaustedException
        with pytest.raises(CodingToolQuotaExhaustedException):
            await provider.complete([Message(role="user", content="hello")])


# ── ClaudeCodeCLIProvider ─────────────────────────────────────────────────────

def _make_claude_provider():
    with patch("shutil.which", return_value="/usr/bin/claude"):
        from synthadoc.providers.coding_tool import ClaudeCodeCLIProvider
        return ClaudeCodeCLIProvider(model=None, timeout=30)


def test_claude_parse_output_valid():
    """Valid JSON output → correct CompletionResponse."""
    import json
    provider = _make_claude_provider()
    raw = json.dumps({
        "result": "The answer is 42.",
        "total_input_tokens": 100,
        "total_output_tokens": 50,
        "is_error": False,
    })
    resp = provider._parse_output(raw)
    assert resp.text == "The answer is 42."
    assert resp.input_tokens == 100
    assert resp.output_tokens == 50


def test_claude_parse_output_is_error_raises():
    """is_error: true in JSON → RuntimeError."""
    import json
    provider = _make_claude_provider()
    raw = json.dumps({"is_error": True, "result": "context length exceeded"})
    with pytest.raises(RuntimeError, match="context length exceeded"):
        provider._parse_output(raw)


def test_claude_parse_output_missing_result_raises():
    """JSON with no result field → ValueError."""
    import json
    provider = _make_claude_provider()
    raw = json.dumps({"is_error": False})
    with pytest.raises(ValueError, match="empty result"):
        provider._parse_output(raw)


def test_claude_parse_output_bad_json_raises():
    """Non-JSON stdout → ValueError."""
    provider = _make_claude_provider()
    with pytest.raises(ValueError, match="malformed JSON"):
        provider._parse_output("not json at all")


def test_claude_is_quota_exhausted_true():
    provider = _make_claude_provider()
    assert provider._is_quota_exhausted("Claude AI usage limit reached") is True
    assert provider._is_quota_exhausted("You've reached your usage cap") is True


def test_claude_is_quota_exhausted_false():
    provider = _make_claude_provider()
    assert provider._is_quota_exhausted("some other error") is False


def test_claude_build_command_no_model():
    provider = _make_claude_provider()
    cmd = provider._build_command()
    assert cmd == ["claude", "-p", "--output-format", "json"]


def test_claude_build_command_with_model():
    with patch("shutil.which", return_value="/usr/bin/claude"):
        from synthadoc.providers.coding_tool import ClaudeCodeCLIProvider
        provider = ClaudeCodeCLIProvider(model="claude-sonnet-4-5", timeout=30)
    cmd = provider._build_command()
    assert "--model" in cmd
    assert "claude-sonnet-4-5" in cmd


# ── OpencodeProvider ──────────────────────────────────────────────────────────

def _make_opencode_provider():
    with patch("shutil.which", return_value="/usr/bin/opencode"):
        from synthadoc.providers.coding_tool import OpencodeProvider
        return OpencodeProvider(model=None, timeout=30)


def test_opencode_parse_output_valid():
    """Valid JSONL with text + step_finish → correct CompletionResponse."""
    import json
    provider = _make_opencode_provider()
    lines = [
        json.dumps({"type": "step_start"}),
        json.dumps({"type": "text", "data": "The answer "}),
        json.dumps({"type": "text", "data": "is 42."}),
        json.dumps({"type": "step_finish", "reason": "stop",
                    "tokens": {"input": 80, "output": 40}}),
    ]
    resp = provider._parse_output("\n".join(lines))
    assert resp.text == "The answer is 42."
    assert resp.input_tokens == 80
    assert resp.output_tokens == 40


def test_opencode_parse_output_no_text_events_raises():
    """JSONL with zero text events → ValueError."""
    import json
    provider = _make_opencode_provider()
    lines = [
        json.dumps({"type": "step_start"}),
        json.dumps({"type": "step_finish", "reason": "stop", "tokens": {}}),
    ]
    with pytest.raises(ValueError, match="no text events"):
        provider._parse_output("\n".join(lines))


def test_opencode_parse_output_step_finish_error_raises():
    """step_finish with reason=error → RuntimeError."""
    import json
    provider = _make_opencode_provider()
    lines = [
        json.dumps({"type": "text", "data": "partial"}),
        json.dumps({"type": "step_finish", "reason": "error"}),
    ]
    with pytest.raises(RuntimeError, match="error"):
        provider._parse_output("\n".join(lines))


def test_opencode_parse_output_truncated_jsonl_raises():
    """Truncated JSONL (no step_finish, no text) → ValueError."""
    provider = _make_opencode_provider()
    with pytest.raises(ValueError, match="no text events"):
        provider._parse_output('{"type": "step_start"}\n{"type": "ste')


def test_opencode_is_quota_exhausted_true():
    provider = _make_opencode_provider()
    assert provider._is_quota_exhausted("Usage limit exceeded for your plan") is True
    assert provider._is_quota_exhausted("quota exceeded") is True


def test_opencode_is_quota_exhausted_false():
    provider = _make_opencode_provider()
    assert provider._is_quota_exhausted("some other error") is False


def test_opencode_build_command_no_model():
    provider = _make_opencode_provider()
    assert provider._build_command() == ["opencode", "run", "--format", "json"]


def test_opencode_build_command_with_model():
    with patch("shutil.which", return_value="/usr/bin/opencode"):
        from synthadoc.providers.coding_tool import OpencodeProvider
        provider = OpencodeProvider(model="anthropic/claude-sonnet-4-5", timeout=30)
    cmd = provider._build_command()
    assert "--model" in cmd
    assert "anthropic/claude-sonnet-4-5" in cmd


# ── Factory + config ──────────────────────────────────────────────────────────

def test_make_provider_claude_code():
    """make_provider returns ClaudeCodeCLIProvider for provider='claude-code'."""
    from synthadoc.config import Config, AgentConfig, AgentsConfig
    cfg = Config(agents=AgentsConfig(
        default=AgentConfig(provider="claude-code", model="")
    ))
    with patch("shutil.which", return_value="/usr/bin/claude"):
        from synthadoc.providers import make_provider
        provider = make_provider("ingest", cfg)
    from synthadoc.providers.coding_tool import ClaudeCodeCLIProvider
    assert isinstance(provider, ClaudeCodeCLIProvider)


def test_make_provider_opencode():
    """make_provider returns OpencodeProvider for provider='opencode'."""
    from synthadoc.config import Config, AgentConfig, AgentsConfig
    cfg = Config(agents=AgentsConfig(
        default=AgentConfig(provider="opencode", model="")
    ))
    with patch("shutil.which", return_value="/usr/bin/opencode"):
        from synthadoc.providers import make_provider
        provider = make_provider("ingest", cfg)
    from synthadoc.providers.coding_tool import OpencodeProvider
    assert isinstance(provider, OpencodeProvider)


def test_config_accepts_claude_code_provider():
    """KNOWN_PROVIDERS includes claude-code and opencode."""
    from synthadoc.config import KNOWN_PROVIDERS
    assert "claude-code" in KNOWN_PROVIDERS
    assert "opencode" in KNOWN_PROVIDERS


# ── Performance benchmarks ────────────────────────────────────────────────────

import time
import json as _json_mod


def test_claude_parse_output_benchmark():
    """_parse_output on a 2000-token response completes in < 50ms."""
    provider = _make_claude_provider()
    big_text = "word " * 1600
    raw = _json_mod.dumps({
        "result": big_text,
        "total_input_tokens": 1000,
        "total_output_tokens": 2000,
        "is_error": False,
    })
    start = time.perf_counter()
    resp = provider._parse_output(raw)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert resp.text == big_text
    assert elapsed_ms < 50, f"_parse_output took {elapsed_ms:.1f}ms (limit: 50ms)"


def test_opencode_parse_output_benchmark():
    """_parse_output on 2000-token JSONL response completes in < 50ms."""
    provider = _make_opencode_provider()
    lines = [
        _json_mod.dumps({"type": "text", "data": "word " * 400})
        for _ in range(4)
    ]
    lines.append(_json_mod.dumps({
        "type": "step_finish", "reason": "stop",
        "tokens": {"input": 1000, "output": 2000},
    }))
    raw = "\n".join(lines)
    start = time.perf_counter()
    resp = provider._parse_output(raw)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert len(resp.text) > 0
    assert elapsed_ms < 50, f"_parse_output took {elapsed_ms:.1f}ms (limit: 50ms)"
