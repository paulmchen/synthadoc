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
async def test_openai_provider_reasoning_content_no_json_returns_empty():
    """If reasoning_content has no JSON array, text must still be empty string (not crash)."""
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
    assert result.text == ""


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
