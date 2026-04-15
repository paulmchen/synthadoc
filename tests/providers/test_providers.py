# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from synthadoc.providers.base import LLMProvider, Message, CompletionResponse
from synthadoc.providers.anthropic import AnthropicProvider
from synthadoc.config import AgentConfig, Config


def test_provider_interface_has_required_methods():
    assert hasattr(LLMProvider, "complete")
    assert hasattr(LLMProvider, "embed")


@pytest.mark.asyncio
async def test_anthropic_provider_complete():
    cfg = AgentConfig(provider="anthropic", model="claude-haiku-4-5-20251001")
    provider = AnthropicProvider(api_key="test-key", config=cfg)
    mock_resp = AsyncMock()
    mock_resp.content = [AsyncMock(text="Paris")]
    mock_resp.usage = AsyncMock(input_tokens=10, output_tokens=5)
    with patch.object(provider._client.messages, "create", new=AsyncMock(return_value=mock_resp)):
        result = await provider.complete(messages=[Message(role="user", content="Capital of France?")])
    assert "Paris" in result.text
    assert result.input_tokens == 10
    assert result.output_tokens == 5
    assert result.total_tokens == 15


@pytest.mark.asyncio
async def test_anthropic_provider_retries_on_rate_limit():
    import anthropic
    cfg = AgentConfig(provider="anthropic", model="claude-haiku-4-5-20251001")
    provider = AnthropicProvider(api_key="test-key", config=cfg)
    call_count = 0

    async def flaky(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise anthropic.RateLimitError(response=MagicMock(status_code=429), body={}, message="rate limit")
        m = AsyncMock()
        m.content = [AsyncMock(text="ok")]
        m.usage = AsyncMock(input_tokens=5, output_tokens=2)
        return m

    with patch.object(provider._client.messages, "create", side_effect=flaky):
        result = await provider.complete(messages=[Message(role="user", content="hi")])
    assert result.text == "ok"
    assert call_count == 3


@pytest.mark.asyncio
async def test_anthropic_provider_raises_on_bad_api_key():
    import anthropic
    cfg = AgentConfig(provider="anthropic", model="claude-haiku-4-5-20251001")
    provider = AnthropicProvider(api_key="bad-key", config=cfg)
    with patch.object(provider._client.messages, "create",
                      side_effect=anthropic.AuthenticationError(
                          response=MagicMock(status_code=401), body={}, message="invalid key")):
        with pytest.raises(anthropic.AuthenticationError):
            await provider.complete(messages=[Message(role="user", content="hi")])


@pytest.mark.asyncio
async def test_provider_raises_after_max_retries():
    import anthropic
    cfg = AgentConfig(provider="anthropic", model="claude-haiku-4-5-20251001")
    provider = AnthropicProvider(api_key="test-key", config=cfg)
    with patch.object(provider._client.messages, "create",
                      side_effect=anthropic.RateLimitError(
                          response=MagicMock(status_code=429), body={}, message="rate limit")):
        with pytest.raises(anthropic.RateLimitError):
            await provider.complete(messages=[Message(role="user", content="hi")])


def _make_cfg(provider: str, model: str) -> "Config":
    from synthadoc.config import Config, AgentsConfig, AgentConfig
    return Config(agents=AgentsConfig(default=AgentConfig(provider=provider, model=model)))


def test_make_provider_missing_anthropic_key_exits(monkeypatch, capsys):
    """make_provider must exit with a helpful message when key is absent."""
    import click
    from synthadoc.providers import make_provider
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    with pytest.raises(click.exceptions.Exit) as exc_info:
        make_provider("ingest", _make_cfg("anthropic", "claude-opus-4-6"))
    assert exc_info.value.exit_code == 1
    err = capsys.readouterr().err
    assert "ANTHROPIC_API_KEY" in err
    assert "console.anthropic.com" in err
    assert "ERR-CFG-001" in err


def test_make_provider_missing_openai_key_exits(monkeypatch, capsys):
    """Same early-exit behaviour for OpenAI provider."""
    import click
    from synthadoc.providers import make_provider
    monkeypatch.setenv("OPENAI_API_KEY", "")
    with pytest.raises(click.exceptions.Exit) as exc_info:
        make_provider("ingest", _make_cfg("openai", "gpt-4o"))
    assert exc_info.value.exit_code == 1
    assert "OPENAI_API_KEY" in capsys.readouterr().err


def test_make_provider_ollama_requires_no_key(monkeypatch):
    """Ollama provider must succeed even when no API key is set."""
    from synthadoc.providers import make_provider
    from synthadoc.providers.ollama import OllamaProvider
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    provider = make_provider("ingest", _make_cfg("ollama", "llama3"))
    assert isinstance(provider, OllamaProvider)


def test_make_provider_missing_gemini_key_exits(monkeypatch, capsys):
    import click
    from synthadoc.providers import make_provider
    monkeypatch.setenv("GEMINI_API_KEY", "")
    with pytest.raises(click.exceptions.Exit) as exc_info:
        make_provider("ingest", _make_cfg("gemini", "gemini-2.0-flash"))
    assert exc_info.value.exit_code == 1
    err = capsys.readouterr().err
    assert "GEMINI_API_KEY" in err
    assert "aistudio.google.com" in err


def test_make_provider_missing_groq_key_exits(monkeypatch, capsys):
    import click
    from synthadoc.providers import make_provider
    monkeypatch.setenv("GROQ_API_KEY", "")
    with pytest.raises(click.exceptions.Exit) as exc_info:
        make_provider("ingest", _make_cfg("groq", "llama-3.3-70b-versatile"))
    assert exc_info.value.exit_code == 1
    err = capsys.readouterr().err
    assert "GROQ_API_KEY" in err
    assert "console.groq.com" in err


def test_make_provider_gemini_uses_openai_provider_with_base_url(monkeypatch):
    from synthadoc.providers import make_provider
    from synthadoc.providers.openai import OpenAIProvider
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    provider = make_provider("ingest", _make_cfg("gemini", "gemini-2.0-flash"))
    assert isinstance(provider, OpenAIProvider)
    assert "generativelanguage" in str(provider._client.base_url)


def test_make_provider_groq_uses_openai_provider_with_base_url(monkeypatch):
    from synthadoc.providers import make_provider
    from synthadoc.providers.openai import OpenAIProvider
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    provider = make_provider("ingest", _make_cfg("groq", "llama-3.3-70b-versatile"))
    assert isinstance(provider, OpenAIProvider)
    assert "groq" in str(provider._client.base_url)


def test_unknown_provider_raises_value_error(capsys):
    import click
    from synthadoc.providers import make_provider
    with pytest.raises(click.exceptions.Exit) as exc_info:
        make_provider("ingest", _make_cfg("unknown_llm", "some-model"))
    assert exc_info.value.exit_code == 1
    assert "ERR-CFG-002" in capsys.readouterr().err


def test_config_rejects_unknown_provider():
    import tempfile, os
    from synthadoc.config import load_config
    from pathlib import Path
    toml_content = b'[agents.default]\nprovider = "bad_provider"\nmodel = "x"\n'
    with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
        f.write(toml_content)
        path = Path(f.name)
    try:
        with pytest.raises(ValueError, match="Unknown provider"):
            load_config(project_config=path)
    finally:
        os.unlink(path)
