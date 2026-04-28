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
async def test_anthropic_provider_propagates_rate_limit_immediately():
    """RateLimitError must not be retried — it should propagate on the first attempt."""
    import anthropic
    cfg = AgentConfig(provider="anthropic", model="claude-haiku-4-5-20251001")
    provider = AnthropicProvider(api_key="test-key", config=cfg)
    call_count = 0

    async def flaky(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise anthropic.RateLimitError(response=MagicMock(status_code=429), body={}, message="rate limit")

    with patch.object(provider._client.messages, "create", side_effect=flaky):
        with pytest.raises(anthropic.RateLimitError):
            await provider.complete(messages=[Message(role="user", content="hi")])
    assert call_count == 1  # raised immediately, no retries


@pytest.mark.asyncio
async def test_anthropic_provider_includes_system_message():
    """System prompt must be forwarded in the kwargs to the Anthropic client."""
    cfg = AgentConfig(provider="anthropic", model="claude-haiku-4-5-20251001")
    provider = AnthropicProvider(api_key="test-key", config=cfg)
    captured: dict = {}

    async def capture(**kwargs):
        captured.update(kwargs)
        mock = MagicMock()
        mock.content = [MagicMock(text="ok")]
        mock.usage = MagicMock(input_tokens=5, output_tokens=2)
        return mock

    with patch.object(provider._client.messages, "create", side_effect=capture):
        await provider.complete(
            messages=[Message(role="user", content="hello")],
            system="You are a helpful assistant.",
        )
    assert captured.get("system") == "You are a helpful assistant."


@pytest.mark.asyncio
async def test_anthropic_provider_retries_on_internal_server_error():
    """InternalServerError is retried; a subsequent success must be returned."""
    import anthropic
    cfg = AgentConfig(provider="anthropic", model="claude-haiku-4-5-20251001")
    provider = AnthropicProvider(api_key="test-key", config=cfg)
    call_count = 0

    async def flaky(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise anthropic.InternalServerError(
                response=MagicMock(status_code=500), body={}, message="server error")
        m = MagicMock()
        m.content = [MagicMock(text="recovered")]
        m.usage = MagicMock(input_tokens=8, output_tokens=3)
        return m

    with patch.object(provider._client.messages, "create", side_effect=flaky):
        with patch("asyncio.sleep", new=AsyncMock()):
            result = await provider.complete(messages=[Message(role="user", content="hi")])

    assert result.text == "recovered"
    assert call_count == 2


@pytest.mark.asyncio
async def test_anthropic_provider_raises_after_all_internal_server_retries():
    """InternalServerError raised on every attempt must propagate after all retries."""
    import anthropic
    cfg = AgentConfig(provider="anthropic", model="claude-haiku-4-5-20251001")
    provider = AnthropicProvider(api_key="test-key", config=cfg)

    exc = anthropic.InternalServerError(
        response=MagicMock(status_code=500), body={}, message="always down")

    with patch.object(provider._client.messages, "create", side_effect=exc):
        with patch("asyncio.sleep", new=AsyncMock()):
            with pytest.raises(anthropic.InternalServerError):
                await provider.complete(messages=[Message(role="user", content="hi")])


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


@pytest.mark.asyncio
async def test_openai_provider_retries_once_on_rate_limit_then_succeeds():
    """A single 429 is retried; the second attempt succeeds and returns a result."""
    import openai
    from synthadoc.providers.openai import OpenAIProvider
    cfg = AgentConfig(provider="gemini", model="gemini-2.5-flash",
                      base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
    provider = OpenAIProvider(api_key="test-key", config=cfg)

    ok_resp = MagicMock()
    ok_resp.choices = [MagicMock()]
    ok_resp.choices[0].message.content = "hello"
    ok_resp.usage.prompt_tokens = 10
    ok_resp.usage.completion_tokens = 5

    rate_limit_exc = openai.RateLimitError(
        message="rate limit", response=MagicMock(status_code=429), body={})
    call_count = 0

    async def flaky(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise rate_limit_exc
        return ok_resp

    with patch.object(provider._client.chat.completions, "create", side_effect=flaky):
        with patch("synthadoc.providers.openai._sleep", new=AsyncMock()):
            result = await provider.complete(messages=[Message(role="user", content="hi")])

    assert result.text == "hello"
    assert call_count == 2


@pytest.mark.asyncio
async def test_openai_provider_raises_after_all_retries_exhausted():
    """When 429s persist across all retries, RateLimitError is re-raised."""
    import openai
    from synthadoc.providers.openai import OpenAIProvider
    cfg = AgentConfig(provider="gemini", model="gemini-2.5-flash",
                      base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
    provider = OpenAIProvider(api_key="test-key", config=cfg)

    rate_limit_exc = openai.RateLimitError(
        message="rate limit", response=MagicMock(status_code=429), body={})

    with patch.object(provider._client.chat.completions, "create",
                      side_effect=rate_limit_exc):
        with patch("synthadoc.providers.openai._sleep", new=AsyncMock()):
            with pytest.raises(openai.RateLimitError):
                await provider.complete(messages=[Message(role="user", content="hi")])


def test_is_daily_quota_error_detects_gemini_body():
    """_is_daily_quota_error must return True for a Gemini per-day quota body."""
    import openai
    from synthadoc.providers.openai import OpenAIProvider
    gemini_body = {
        "error": {
            "code": 429,
            "details": [{
                "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                "violations": [{
                    "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                    "quotaValue": "20",
                }]
            }]
        }
    }
    exc = openai.RateLimitError(
        message="quota exceeded", response=MagicMock(status_code=429), body=gemini_body)
    assert OpenAIProvider._is_daily_quota_error(exc) is True


def test_is_daily_quota_error_returns_false_for_per_minute():
    """_is_daily_quota_error must return False for a plain per-minute rate limit."""
    import openai
    from synthadoc.providers.openai import OpenAIProvider
    exc = openai.RateLimitError(
        message="rate limited, please retry", response=MagicMock(status_code=429), body={})
    assert OpenAIProvider._is_daily_quota_error(exc) is False


@pytest.mark.asyncio
async def test_openai_provider_daily_quota_raises_immediately_without_retry():
    """A Gemini daily-quota 429 must raise DailyQuotaExhaustedException immediately —
    no sleep, no retry, to avoid wasting 65 s and burning one more scarce daily request."""
    import openai
    from synthadoc.providers.openai import OpenAIProvider
    from synthadoc.errors import DailyQuotaExhaustedException
    cfg = AgentConfig(provider="gemini", model="gemini-2.5-flash-lite",
                      base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
    provider = OpenAIProvider(api_key="test-key", config=cfg)

    gemini_body = {
        "error": {
            "details": [{
                "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]
            }]
        }
    }
    daily_exc = openai.RateLimitError(
        message="daily quota", response=MagicMock(status_code=429), body=gemini_body)

    call_count = 0
    sleep_mock = AsyncMock()

    async def flaky(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise daily_exc

    with patch.object(provider._client.chat.completions, "create", side_effect=flaky):
        with patch("synthadoc.providers.openai._sleep", new=sleep_mock):
            with pytest.raises(DailyQuotaExhaustedException):
                await provider.complete(messages=[Message(role="user", content="hi")])

    assert call_count == 1, "daily quota must not be retried"
    sleep_mock.assert_not_called()


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


def test_make_provider_missing_minimax_key_exits(monkeypatch, capsys):
    import click
    from synthadoc.providers import make_provider
    monkeypatch.setenv("MINIMAX_API_KEY", "")
    with pytest.raises(click.exceptions.Exit) as exc_info:
        make_provider("ingest", _make_cfg("minimax", "MiniMax-M2.5"))
    assert exc_info.value.exit_code == 1
    err = capsys.readouterr().err
    assert "MINIMAX_API_KEY" in err
    assert "platform.minimax.io" in err


def test_make_provider_minimax_uses_openai_provider_with_base_url(monkeypatch):
    from synthadoc.providers import make_provider
    from synthadoc.providers.openai import OpenAIProvider
    monkeypatch.setenv("MINIMAX_API_KEY", "test-minimax-key")
    provider = make_provider("ingest", _make_cfg("minimax", "MiniMax-M2.5"))
    assert isinstance(provider, OpenAIProvider)
    assert "minimax.io" in str(provider._client.base_url)
    assert provider.supports_vision is True   # M2.5 is natively multimodal


def test_make_provider_gemini_uses_openai_provider_with_base_url(monkeypatch):
    from synthadoc.providers import make_provider
    from synthadoc.providers.openai import OpenAIProvider
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    provider = make_provider("ingest", _make_cfg("gemini", "gemini-2.0-flash"))
    assert isinstance(provider, OpenAIProvider)
    assert "generativelanguage" in str(provider._client.base_url)
    assert provider.supports_vision is True


def test_make_provider_groq_uses_openai_provider_with_base_url(monkeypatch):
    from synthadoc.providers import make_provider
    from synthadoc.providers.openai import OpenAIProvider
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    provider = make_provider("ingest", _make_cfg("groq", "llama-3.3-70b-versatile"))
    assert isinstance(provider, OpenAIProvider)
    assert "groq" in str(provider._client.base_url)
    assert provider.supports_vision is False


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


from synthadoc.providers.openai import OpenAIProvider


@pytest.mark.asyncio
async def test_openai_provider_complete():
    """OpenAIProvider.complete() must return a correctly populated CompletionResponse."""
    cfg = AgentConfig(provider="openai", model="gpt-4o-mini")
    provider = OpenAIProvider(api_key="test-key", config=cfg)

    mock_choice = MagicMock()
    mock_choice.message.content = "The answer is 42."
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage.prompt_tokens = 15
    mock_resp.usage.completion_tokens = 8

    with patch.object(provider._client.chat.completions, "create",
                      new=AsyncMock(return_value=mock_resp)):
        result = await provider.complete(
            messages=[Message(role="user", content="What is the answer?")]
        )
    assert result.text == "The answer is 42."
    assert result.input_tokens == 15
    assert result.output_tokens == 8
    assert result.total_tokens == 23


@pytest.mark.asyncio
async def test_openai_provider_includes_system_message():
    """If a system message is provided, it must be prepended to the messages list."""
    cfg = AgentConfig(provider="openai", model="gpt-4o-mini")
    provider = OpenAIProvider(api_key="test-key", config=cfg)

    mock_choice = MagicMock()
    mock_choice.message.content = "ok"
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage.prompt_tokens = 10
    mock_resp.usage.completion_tokens = 2

    captured: dict = {}

    async def capture(*args, **kwargs):
        captured["messages"] = kwargs.get("messages", [])
        return mock_resp

    with patch.object(provider._client.chat.completions, "create", side_effect=capture):
        await provider.complete(
            messages=[Message(role="user", content="hello")],
            system="You are a helpful assistant.",
        )
    assert captured["messages"][0] == {"role": "system", "content": "You are a helpful assistant."}
    assert captured["messages"][1]["role"] == "user"


@pytest.mark.asyncio
async def test_openai_provider_empty_content_returns_empty_string():
    """If the model returns None content with no reasoning fallback, text must be empty string."""
    cfg = AgentConfig(provider="openai", model="gpt-4o-mini")
    provider = OpenAIProvider(api_key="test-key", config=cfg)

    mock_choice = MagicMock()
    mock_choice.message.content = None
    mock_choice.message.model_extra = {}
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage.prompt_tokens = 5
    mock_resp.usage.completion_tokens = 0

    with patch.object(provider._client.chat.completions, "create",
                      new=AsyncMock(return_value=mock_resp)):
        result = await provider.complete(
            messages=[Message(role="user", content="hi")]
        )
    assert result.text == ""


@pytest.mark.asyncio
async def test_openai_provider_strips_think_tags_from_content():
    """Reasoning models (e.g. MiniMax M2.x) prefix content with <think>...</think>.
    The provider must strip those tags so callers receive clean text."""
    cfg = AgentConfig(provider="minimax", model="MiniMax-M2.5",
                      base_url="https://api.minimax.io/v1")
    provider = OpenAIProvider(api_key="test-key", config=cfg)

    mock_choice = MagicMock()
    mock_choice.message.content = '<think>Let me break this down...</think>["What is X?", "How does X work?"]'
    mock_choice.message.model_extra = {}
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage.prompt_tokens = 20
    mock_resp.usage.completion_tokens = 15

    with patch.object(provider._client.chat.completions, "create",
                      new=AsyncMock(return_value=mock_resp)):
        result = await provider.complete(
            messages=[Message(role="user", content="Tell me about X")]
        )
    assert result.text == '["What is X?", "How does X work?"]'


@pytest.mark.asyncio
async def test_openai_provider_extracts_json_from_reasoning_content():
    """MiniMax-style reasoning models return content=null with JSON in reasoning_content.
    The provider must extract the last JSON array from reasoning_content as a fallback."""
    cfg = AgentConfig(provider="minimax", model="MiniMax-M2.5",
                      base_url="https://api.minimax.io/v1")
    provider = OpenAIProvider(api_key="test-key", config=cfg)

    mock_choice = MagicMock()
    mock_choice.message.content = None
    mock_choice.message.model_extra = {
        "reasoning_content": (
            'I need to break this into sub-questions. '
            'Here are the relevant aspects to cover: '
            '["What is X?", "How does X work?", "What are X applications?"]'
        )
    }
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage.prompt_tokens = 20
    mock_resp.usage.completion_tokens = 0

    with patch.object(provider._client.chat.completions, "create",
                      new=AsyncMock(return_value=mock_resp)):
        result = await provider.complete(
            messages=[Message(role="user", content="Tell me about X")]
        )
    assert result.text == '["What is X?", "How does X work?", "What are X applications?"]'


@pytest.mark.asyncio
async def test_openai_provider_reasoning_content_no_json_returns_prose():
    """If reasoning_content has no JSON array, the prose text is returned as-is (prose answer fallback)."""
    cfg = AgentConfig(provider="minimax", model="MiniMax-M2.5",
                      base_url="https://api.minimax.io/v1")
    provider = OpenAIProvider(api_key="test-key", config=cfg)

    mock_choice = MagicMock()
    mock_choice.message.content = None
    mock_choice.message.model_extra = {
        "reasoning_content": "I am thinking about this question at length..."
    }
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage.prompt_tokens = 10
    mock_resp.usage.completion_tokens = 0

    with patch.object(provider._client.chat.completions, "create",
                      new=AsyncMock(return_value=mock_resp)):
        result = await provider.complete(
            messages=[Message(role="user", content="hi")]
        )
    assert result.text == "I am thinking about this question at length..."


@pytest.mark.asyncio
async def test_openai_provider_reasoning_content_strips_think_tags_then_returns_prose():
    """Think tags are stripped from reasoning_content before returning prose answer."""
    cfg = AgentConfig(provider="minimax", model="MiniMax-M2.5",
                      base_url="https://api.minimax.io/v1")
    provider = OpenAIProvider(api_key="test-key", config=cfg)

    mock_choice = MagicMock()
    mock_choice.message.content = None
    mock_choice.message.model_extra = {
        "reasoning_content": "<think>internal reasoning here</think>Moore's Law states that transistor counts double roughly every two years."
    }
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage.prompt_tokens = 10
    mock_resp.usage.completion_tokens = 0

    with patch.object(provider._client.chat.completions, "create",
                      new=AsyncMock(return_value=mock_resp)):
        result = await provider.complete(
            messages=[Message(role="user", content="What is Moore's Law?")]
        )
    assert result.text == "Moore's Law states that transistor counts double roughly every two years."


@pytest.mark.asyncio
async def test_openai_provider_raises_on_null_choices():
    """choices=null from providers like MiniMax must raise RuntimeError, not TypeError."""
    cfg = AgentConfig(provider="minimax", model="MiniMax-M2.5",
                      base_url="https://api.minimax.io/v1")
    provider = OpenAIProvider(api_key="test-key", config=cfg)

    mock_resp = MagicMock()
    mock_resp.choices = None
    mock_resp.model_extra = {"base_resp": {"status_code": 1000, "status_msg": "timeout"}}

    with patch.object(provider._client.chat.completions, "create",
                      new=AsyncMock(return_value=mock_resp)):
        with pytest.raises(RuntimeError, match="choices=null"):
            await provider.complete(messages=[Message(role="user", content="hi")])


@pytest.mark.asyncio
async def test_openai_provider_passes_timeout_to_create():
    """timeout > 0 is forwarded to chat.completions.create()."""
    cfg = AgentConfig(provider="minimax", model="MiniMax-M2.5",
                      base_url="https://api.minimax.io/v1")
    provider = OpenAIProvider(api_key="test-key", config=cfg, timeout=90)

    mock_choice = MagicMock()
    mock_choice.message.content = "answer"
    mock_choice.message.model_extra = {}
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage.prompt_tokens = 10
    mock_resp.usage.completion_tokens = 5

    mock_create = AsyncMock(return_value=mock_resp)
    with patch.object(provider._client.chat.completions, "create", new=mock_create):
        await provider.complete(messages=[Message(role="user", content="hi")])

    _, kwargs = mock_create.call_args
    assert kwargs.get("timeout") == 90


@pytest.mark.asyncio
async def test_openai_provider_passes_none_timeout_when_zero():
    """timeout=0 (no limit) sends timeout=None to create() so the SDK uses its default."""
    cfg = AgentConfig(provider="gemini", model="gemini-2.5-flash-lite",
                      base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
    provider = OpenAIProvider(api_key="test-key", config=cfg, timeout=0)

    mock_choice = MagicMock()
    mock_choice.message.content = "answer"
    mock_choice.message.model_extra = {}
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage.prompt_tokens = 10
    mock_resp.usage.completion_tokens = 5

    mock_create = AsyncMock(return_value=mock_resp)
    with patch.object(provider._client.chat.completions, "create", new=mock_create):
        await provider.complete(messages=[Message(role="user", content="hi")])

    _, kwargs = mock_create.call_args
    assert kwargs.get("timeout") is None


@pytest.mark.asyncio
async def test_openai_provider_api_timeout_error_is_logged_and_raised():
    """APITimeoutError is logged with config hint and re-raised."""
    import openai
    cfg = AgentConfig(provider="minimax", model="MiniMax-M2.5",
                      base_url="https://api.minimax.io/v1")
    provider = OpenAIProvider(api_key="test-key", config=cfg, timeout=90)

    with patch.object(provider._client.chat.completions, "create",
                      new=AsyncMock(side_effect=openai.APITimeoutError(request=MagicMock()))):
        with pytest.raises(openai.APITimeoutError):
            await provider.complete(messages=[Message(role="user", content="hi")])


@pytest.mark.asyncio
async def test_openai_provider_uses_custom_base_url():
    """Providers like Groq and Gemini pass a base_url — verify it is forwarded to AsyncOpenAI."""
    cfg = AgentConfig(provider="groq", model="llama3-8b-8192",
                      base_url="https://api.groq.com/openai/v1")
    with patch("synthadoc.providers.openai.AsyncOpenAI") as mock_client_cls:
        OpenAIProvider(api_key="test-key", config=cfg)
    mock_client_cls.assert_called_once_with(
        api_key="test-key", base_url="https://api.groq.com/openai/v1"
    )


def test_to_openai_content_converts_anthropic_image_block():
    """Anthropic base64 image block must be converted to OpenAI image_url format."""
    block = {"type": "image", "source": {
        "type": "base64", "media_type": "image/png", "data": "abc123"
    }}
    result = OpenAIProvider._to_openai_content([block])
    assert result == [{"type": "image_url",
                       "image_url": {"url": "data:image/png;base64,abc123"}}]


def test_to_openai_content_passes_text_block_through():
    """Text content blocks must be forwarded unchanged."""
    block = {"type": "text", "text": "hello world"}
    result = OpenAIProvider._to_openai_content([block])
    assert result == [block]


def test_to_openai_content_mixed_blocks():
    """Mixed image + text blocks — image converted, text unchanged."""
    blocks = [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "xyz"}},
        {"type": "text", "text": "Describe this image."},
    ]
    result = OpenAIProvider._to_openai_content(blocks)
    assert result[0] == {"type": "image_url",
                         "image_url": {"url": "data:image/jpeg;base64,xyz"}}
    assert result[1] == {"type": "text", "text": "Describe this image."}


def test_to_openai_content_string_passthrough():
    """Plain string content must be returned unchanged (no list wrapping)."""
    assert OpenAIProvider._to_openai_content("hello") == "hello"


@pytest.mark.asyncio
async def test_openai_provider_vision_call_uses_image_url_format():
    """Vision messages from IngestAgent (Anthropic format) must be converted before sending."""
    from synthadoc.providers.base import Message
    cfg = AgentConfig(provider="gemini", model="gemini-2.0-flash",
                      base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
    provider = OpenAIProvider(api_key="test-key", config=cfg)

    mock_choice = MagicMock()
    mock_choice.message.content = "A diagram showing X."
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage.prompt_tokens = 20
    mock_resp.usage.completion_tokens = 10

    captured: dict = {}

    async def capture(*args, **kwargs):
        captured["messages"] = kwargs.get("messages", [])
        return mock_resp

    anthropic_content = [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "AAAA"}},
        {"type": "text", "text": "What is in this image?"},
    ]
    with patch.object(provider._client.chat.completions, "create", side_effect=capture):
        await provider.complete(messages=[Message(role="user", content=anthropic_content)])

    sent_content = captured["messages"][0]["content"]
    assert sent_content[0]["type"] == "image_url"
    assert sent_content[0]["image_url"]["url"] == "data:image/png;base64,AAAA"
    assert sent_content[1] == {"type": "text", "text": "What is in this image?"}


def test_make_provider_missing_deepseek_key_exits(monkeypatch, capsys):
    import click
    from synthadoc.providers import make_provider
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    with pytest.raises(click.exceptions.Exit) as exc_info:
        make_provider("ingest", _make_cfg("deepseek", "deepseek-chat"))
    assert exc_info.value.exit_code == 1
    err = capsys.readouterr().err
    assert "DEEPSEEK_API_KEY" in err
    assert "platform.deepseek.com" in err


def test_make_provider_deepseek_uses_openai_provider_with_base_url(monkeypatch):
    from synthadoc.providers import make_provider
    from synthadoc.providers.openai import OpenAIProvider
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek-key")
    provider = make_provider("ingest", _make_cfg("deepseek", "deepseek-chat"))
    assert isinstance(provider, OpenAIProvider)
    assert "api.deepseek.com" in str(provider._client.base_url)
    assert provider.supports_vision is False  # DeepSeek is text-only


@pytest.mark.asyncio
async def test_openai_provider_deepseek_r1_think_tags_stripped():
    """DeepSeek-R1 embeds <think>...</think> in the content field; they must be stripped."""
    cfg = AgentConfig(provider="deepseek", model="deepseek-reasoner",
                      base_url="https://api.deepseek.com/v1")
    provider = OpenAIProvider(api_key="test-key", config=cfg)

    mock_choice = MagicMock()
    mock_choice.message.content = (
        "<think>Let me reason step by step about this.</think>"
        "The capital of France is Paris."
    )
    mock_choice.message.model_extra = {}
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_resp.usage.prompt_tokens = 12
    mock_resp.usage.completion_tokens = 8

    with patch.object(provider._client.chat.completions, "create",
                      new=AsyncMock(return_value=mock_resp)):
        result = await provider.complete(
            messages=[Message(role="user", content="What is the capital of France?")]
        )
    assert result.text == "The capital of France is Paris."
    assert "<think>" not in result.text


def test_classify_llm_error_returns_401_for_auth_error():
    """AuthenticationError (401) must return a 401 HTTPException, not fall through to 502."""
    import openai
    from synthadoc.integration.http_server import _classify_llm_error
    exc = openai.AuthenticationError(
        message="Authentication Fails, Your api key is invalid",
        response=MagicMock(status_code=401),
        body={"error": {"message": "Authentication Fails, Your api key: ****2YES is invalid",
                        "type": "authentication_error"}},
    )
    result = _classify_llm_error(exc)
    assert result is not None
    assert result.status_code == 401
    assert "401" in result.detail


def test_classify_llm_error_names_deepseek_key_in_401():
    """A DeepSeek 401 must name DEEPSEEK_API_KEY in the error detail."""
    import openai
    from synthadoc.integration.http_server import _classify_llm_error
    exc = openai.AuthenticationError(
        message="Authentication Fails from api.deepseek.com",
        response=MagicMock(status_code=401),
        body={},
    )
    result = _classify_llm_error(exc)
    assert result is not None
    assert "DEEPSEEK_API_KEY" in result.detail


def test_classify_llm_error_names_gemini_key_in_401():
    """A Gemini 401 must name GEMINI_API_KEY in the error detail."""
    import openai
    from synthadoc.integration.http_server import _classify_llm_error
    exc = openai.AuthenticationError(
        message="Invalid key for generativelanguage.googleapis.com",
        response=MagicMock(status_code=401),
        body={},
    )
    result = _classify_llm_error(exc)
    assert result is not None
    assert "GEMINI_API_KEY" in result.detail


def test_classify_llm_error_returns_none_for_unrecognised():
    """Unrecognised exception (no status_code, not DailyQuota) returns None → caller emits 502."""
    from synthadoc.integration.http_server import _classify_llm_error
    result = _classify_llm_error(ValueError("something unexpected"))
    assert result is None


@pytest.mark.asyncio
async def test_ollama_provider_uses_eval_count_for_output_tokens():
    """OllamaProvider must read eval_count from the response for output_tokens."""
    from synthadoc.providers.ollama import OllamaProvider
    cfg = AgentConfig(provider="ollama", model="llama3")
    provider = OllamaProvider(config=cfg)

    fake_response = {
        "message": {"content": "The answer is 42."},
        "prompt_eval_count": 12,
        "eval_count": 7,
    }

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=MagicMock(
        status_code=200,
        raise_for_status=MagicMock(),
        json=MagicMock(return_value=fake_response),
    ))):
        result = await provider.complete(messages=[Message(role="user", content="hi")])

    assert result.text == "The answer is 42."
    assert result.input_tokens == 12
    assert result.output_tokens == 7
    assert result.total_tokens == 19
