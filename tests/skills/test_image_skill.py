# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import base64
import pytest
from unittest.mock import AsyncMock
from synthadoc.skills.image.scripts.main import ImageSkill
from synthadoc.providers.base import CompletionResponse


def _make_provider(text: str, input_tokens: int = 30, output_tokens: int = 15) -> AsyncMock:
    provider = AsyncMock()
    provider.supports_vision = True
    provider.complete = AsyncMock(return_value=CompletionResponse(
        text=text, input_tokens=input_tokens, output_tokens=output_tokens,
    ))
    return provider


@pytest.mark.asyncio
async def test_image_skill_returns_extracted_text(tmp_path):
    """ImageSkill.extract() calls vision LLM and returns text in ExtractedContent."""
    img = tmp_path / "diagram.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

    provider = _make_provider("A CPU architecture diagram.")
    skill = ImageSkill(provider=provider)
    result = await skill.extract(str(img))

    assert result.text == "A CPU architecture diagram."
    assert result.source_path == str(img)


@pytest.mark.asyncio
async def test_image_skill_sends_base64_to_provider(tmp_path):
    """Provider receives the image as a base64 multimodal message."""
    img = tmp_path / "photo.jpg"
    img.write_bytes(b"\xff\xd8\xff" + b"\x00" * 50)
    expected_b64 = base64.b64encode(img.read_bytes()).decode()

    provider = _make_provider("A photo.")
    skill = ImageSkill(provider=provider)
    await skill.extract(str(img))

    call_args = provider.complete.call_args
    messages = call_args.kwargs.get("messages") or call_args.args[0]
    content = messages[0].content
    assert isinstance(content, list)
    image_block = next(b for b in content if isinstance(b, dict) and b.get("type") == "image")
    assert image_block["source"]["data"] == expected_b64
    assert image_block["source"]["media_type"] == "image/jpeg"


@pytest.mark.asyncio
async def test_image_skill_token_counts_in_metadata(tmp_path):
    """Token counts from the vision LLM call are returned in ExtractedContent.metadata."""
    img = tmp_path / "chart.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

    provider = _make_provider("A bar chart.", input_tokens=42, output_tokens=18)
    skill = ImageSkill(provider=provider)
    result = await skill.extract(str(img))

    assert result.metadata["tokens_input"] == 42
    assert result.metadata["tokens_output"] == 18


@pytest.mark.asyncio
async def test_image_skill_raises_without_provider(tmp_path):
    """ImageSkill.extract() raises ValueError when no provider is configured."""
    img = tmp_path / "diagram.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

    skill = ImageSkill()
    with pytest.raises(ValueError, match="provider"):
        await skill.extract(str(img))


@pytest.mark.asyncio
async def test_image_skill_raises_for_text_only_provider(tmp_path):
    """ImageSkill.extract() raises NotImplementedError when provider doesn't support vision."""
    img = tmp_path / "diagram.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

    provider = AsyncMock()
    provider.supports_vision = False
    skill = ImageSkill(provider=provider)
    with pytest.raises(NotImplementedError, match="vision"):
        await skill.extract(str(img))
