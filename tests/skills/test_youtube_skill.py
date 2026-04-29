# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import asyncio
import pytest
from unittest.mock import patch, AsyncMock
from synthadoc.skills.base import ExtractedContent


def _load_skill():
    from synthadoc.agents.skill_agent import SkillAgent
    from pathlib import Path
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    (tmp / "wiki").mkdir()
    agent = SkillAgent(wiki_root=tmp)
    return agent.get_skill("youtube")


def _fake_transcript():
    from types import SimpleNamespace
    return [
        SimpleNamespace(text="Hello world.", start=0.0, duration=2.0),
        SimpleNamespace(text="This is a test.", start=2.0, duration=3.0),
    ]


@pytest.mark.asyncio
async def test_extract_returns_transcript_text():
    """Transcript text is joined with [MM:SS] timestamp prefixes on each snippet."""
    skill = _load_skill()
    with patch("synthadoc.skills.youtube.scripts.main.asyncio.to_thread",
               new=AsyncMock(return_value=_fake_transcript())):
        result = await skill.extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert result.text == "[0:00] Hello world. [0:02] This is a test."
    assert result.source_path == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


@pytest.mark.asyncio
async def test_extract_no_transcript_returns_empty():
    """NoTranscriptFound must return empty ExtractedContent, not raise."""
    from youtube_transcript_api import NoTranscriptFound
    skill = _load_skill()
    with patch("synthadoc.skills.youtube.scripts.main.asyncio.to_thread",
               side_effect=NoTranscriptFound("dQw4w9WgXcQ", [], [])):
        result = await skill.extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert result.text == ""
    assert result.metadata.get("no_transcript") is True


@pytest.mark.asyncio
async def test_extract_video_unavailable_returns_empty():
    """VideoUnavailable must return empty ExtractedContent, not raise."""
    from youtube_transcript_api import VideoUnavailable
    skill = _load_skill()
    with patch("synthadoc.skills.youtube.scripts.main.asyncio.to_thread",
               side_effect=VideoUnavailable("dQw4w9WgXcQ")):
        result = await skill.extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert result.text == ""


@pytest.mark.asyncio
async def test_extract_invalid_url_returns_empty():
    """URL from which no video ID can be parsed must return empty content silently."""
    skill = _load_skill()
    result = await skill.extract("https://www.youtube.com/")
    assert result.text == ""


def test_extract_video_id_from_watch_url():
    """Standard watch URL: extract video ID from ?v= query param."""
    from synthadoc.skills.youtube.scripts.main import _extract_video_id
    assert _extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert _extract_video_id("https://www.youtube.com/watch?v=abc123&t=30s") == "abc123"


def test_extract_video_id_from_youtu_be():
    """Short youtu.be URL: extract video ID from path."""
    from synthadoc.skills.youtube.scripts.main import _extract_video_id
    assert _extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert _extract_video_id("https://youtu.be/abc123?t=42") == "abc123"


def test_extract_video_id_from_embed_url():
    """Embed URL: extract video ID from /embed/ path segment."""
    from synthadoc.skills.youtube.scripts.main import _extract_video_id
    assert _extract_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_extract_video_id_from_shorts_url():
    """Shorts URL: extract video ID from /shorts/ path segment."""
    from synthadoc.skills.youtube.scripts.main import _extract_video_id
    assert _extract_video_id("https://www.youtube.com/shorts/vVeaJMd4wa8") == "vVeaJMd4wa8"


def test_extract_video_id_from_live_url():
    """Live URL: extract video ID from /live/ path segment."""
    from synthadoc.skills.youtube.scripts.main import _extract_video_id
    assert _extract_video_id("https://www.youtube.com/live/abc123xyz") == "abc123xyz"


def test_extract_video_id_returns_none_for_invalid():
    """URL with no recognisable video ID must return None."""
    from synthadoc.skills.youtube.scripts.main import _extract_video_id
    assert _extract_video_id("https://www.youtube.com/channel/UC1234") is None
    assert _extract_video_id("https://www.youtube.com/") is None


@pytest.mark.asyncio
async def test_extract_runs_in_thread():
    """Transcript fetch must use asyncio.to_thread to avoid blocking the event loop."""
    skill = _load_skill()
    with patch("synthadoc.skills.youtube.scripts.main.asyncio.to_thread",
               new=AsyncMock(return_value=_fake_transcript())) as mock_thread:
        await skill.extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    mock_thread.assert_called_once()


@pytest.mark.asyncio
async def test_metadata_contains_video_id_and_url():
    """ExtractedContent metadata must include video_id and url keys."""
    skill = _load_skill()
    with patch("synthadoc.skills.youtube.scripts.main.asyncio.to_thread",
               new=AsyncMock(return_value=_fake_transcript())):
        result = await skill.extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert result.metadata["video_id"] == "dQw4w9WgXcQ"
    assert result.metadata["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_format_timestamp():
    """_format_timestamp converts float seconds to MM:SS string."""
    from synthadoc.skills.youtube.scripts.main import _format_timestamp
    assert _format_timestamp(0.0) == "0:00"
    assert _format_timestamp(2.5) == "0:02"
    assert _format_timestamp(60.0) == "1:00"
    assert _format_timestamp(90.0) == "1:30"
    assert _format_timestamp(3661.0) == "61:01"


@pytest.mark.asyncio
async def test_transcript_text_contains_timestamps():
    """Each snippet must be prefixed with its [MM:SS] timestamp in the output text."""
    from types import SimpleNamespace
    skill = _load_skill()
    snippets = [
        SimpleNamespace(text="Moore's Law.", start=0.0, duration=3.0),
        SimpleNamespace(text="Transistor scaling.", start=90.0, duration=4.0),
        SimpleNamespace(text="End of scaling.", start=3661.0, duration=5.0),
    ]
    with patch("synthadoc.skills.youtube.scripts.main.asyncio.to_thread",
               new=AsyncMock(return_value=snippets)):
        result = await skill.extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert "[0:00] Moore's Law." in result.text
    assert "[1:30] Transistor scaling." in result.text
    assert "[61:01] End of scaling." in result.text


def test_is_cjk_dominant_true():
    from synthadoc.skills.youtube.scripts.main import _is_cjk_dominant
    assert _is_cjk_dominant("这是一段中文文字，用于测试CJK字符检测功能。") is True


def test_is_cjk_dominant_false():
    from synthadoc.skills.youtube.scripts.main import _is_cjk_dominant
    assert _is_cjk_dominant("This is plain English text with no CJK characters.") is False


def test_is_cjk_dominant_mixed_under_threshold():
    from synthadoc.skills.youtube.scripts.main import _is_cjk_dominant
    # 1 CJK char in 100 chars total = 1% — below 10% threshold
    text = "A" * 99 + "中"
    assert _is_cjk_dominant(text) is False


def test_is_cjk_dominant_empty_string():
    from synthadoc.skills.youtube.scripts.main import _is_cjk_dominant
    assert _is_cjk_dominant("") is False


@pytest.mark.asyncio
async def test_extract_without_provider_returns_raw_transcript():
    """Without a provider, extract() returns raw transcript — existing behaviour."""
    skill = _load_skill()  # no provider
    with patch("synthadoc.skills.youtube.scripts.main.asyncio.to_thread",
               new=AsyncMock(return_value=_fake_transcript())):
        result = await skill.extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert "## Executive Summary" not in result.text
    assert result.metadata.get("has_summary") is not True


@pytest.mark.asyncio
async def test_extract_with_provider_includes_executive_summary():
    """With a provider, extract() returns text starting with ## Executive Summary."""
    from synthadoc.providers.base import CompletionResponse
    from synthadoc.skills.youtube.scripts.main import YoutubeSkill

    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text="A video about computing history.\n- Topic one\n- Topic two\nKey takeaway: history matters.",
        input_tokens=100, output_tokens=50,
    )
    skill = YoutubeSkill(provider=provider)
    with patch("synthadoc.skills.youtube.scripts.main.asyncio.to_thread",
               new=AsyncMock(return_value=_fake_transcript())):
        result = await skill.extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert result.text.startswith("## Executive Summary")


@pytest.mark.asyncio
async def test_extract_with_provider_has_summary_metadata():
    """With a provider, metadata must include has_summary=True."""
    from synthadoc.providers.base import CompletionResponse
    from synthadoc.skills.youtube.scripts.main import YoutubeSkill

    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text="Summary text.", input_tokens=10, output_tokens=10,
    )
    skill = YoutubeSkill(provider=provider)
    with patch("synthadoc.skills.youtube.scripts.main.asyncio.to_thread",
               new=AsyncMock(return_value=_fake_transcript())):
        result = await skill.extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert result.metadata.get("has_summary") is True


@pytest.mark.asyncio
async def test_extract_with_provider_includes_transcript_section():
    """Structured output must include ## Transcript section with [MM:SS] entries."""
    from synthadoc.providers.base import CompletionResponse
    from synthadoc.skills.youtube.scripts.main import YoutubeSkill

    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text="Summary text.", input_tokens=10, output_tokens=10,
    )
    skill = YoutubeSkill(provider=provider)
    with patch("synthadoc.skills.youtube.scripts.main.asyncio.to_thread",
               new=AsyncMock(return_value=_fake_transcript())):
        result = await skill.extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert "## Transcript" in result.text
    assert "[0:00]" in result.text


@pytest.mark.asyncio
async def test_extract_summary_llm_failure_falls_back():
    """If the summary LLM call raises, extract() falls back to raw transcript."""
    from synthadoc.skills.youtube.scripts.main import YoutubeSkill

    provider = AsyncMock()
    provider.complete.side_effect = RuntimeError("LLM unavailable")
    skill = YoutubeSkill(provider=provider)
    with patch("synthadoc.skills.youtube.scripts.main.asyncio.to_thread",
               new=AsyncMock(return_value=_fake_transcript())):
        result = await skill.extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert "## Executive Summary" not in result.text
    assert result.metadata.get("has_summary") is not True


@pytest.mark.asyncio
async def test_summary_uses_limit_200_for_latin():
    """Latin transcript → prompt must contain '200 words'."""
    from synthadoc.providers.base import CompletionResponse
    from synthadoc.skills.youtube.scripts.main import YoutubeSkill

    provider = AsyncMock()
    captured_prompt = []

    async def capture(messages, **kwargs):
        captured_prompt.append(messages[0].content)
        return CompletionResponse(text="ok", input_tokens=5, output_tokens=5)

    provider.complete.side_effect = capture
    skill = YoutubeSkill(provider=provider)
    with patch("synthadoc.skills.youtube.scripts.main.asyncio.to_thread",
               new=AsyncMock(return_value=_fake_transcript())):
        await skill.extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert "200 words" in captured_prompt[0]


@pytest.mark.asyncio
async def test_summary_uses_limit_400_for_cjk():
    """CJK transcript → prompt must contain '400 words'."""
    from types import SimpleNamespace
    from synthadoc.providers.base import CompletionResponse
    from synthadoc.skills.youtube.scripts.main import YoutubeSkill

    provider = AsyncMock()
    captured_prompt = []

    async def capture(messages, **kwargs):
        captured_prompt.append(messages[0].content)
        return CompletionResponse(text="好的", input_tokens=5, output_tokens=5)

    provider.complete.side_effect = capture

    cjk_snippets = [
        SimpleNamespace(text="这是关于计算机历史的视频。晶体管的发明改变了世界。", start=0.0, duration=5.0),
        SimpleNamespace(text="摩尔定律预测了集成电路上晶体管数量的增长趋势。", start=5.0, duration=5.0),
    ]
    skill = YoutubeSkill(provider=provider)
    with patch("synthadoc.skills.youtube.scripts.main.asyncio.to_thread",
               new=AsyncMock(return_value=cjk_snippets)):
        await skill.extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert "400 words" in captured_prompt[0]
