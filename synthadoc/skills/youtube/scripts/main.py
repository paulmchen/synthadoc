# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlparse, parse_qs

from synthadoc.skills.base import BaseSkill, ExtractedContent, SkillMeta
import re

_CJK_RE = re.compile(
    r'[一-鿿぀-ゟ゠-ヿ가-힯]'
)

_YOUTUBE_SUMMARY_PROMPT = (
    "Summarise this YouTube video transcript for a knowledge wiki.\n"
    "Write no more than {limit} words.\n"
    "- One or two sentences: what the video is about\n"
    "- Bullet list: main topics covered\n"
    "- One sentence: key takeaway\n\n"
    "Markdown bullets only. No headings. No filler phrases.\n\n"
    "Transcript:\n{transcript}"
)


def _is_cjk_dominant(text: str) -> bool:
    if not text:
        return False
    return len(_CJK_RE.findall(text)) / len(text) > 0.10


logger = logging.getLogger(__name__)


def _format_timestamp(seconds: float) -> str:
    """Convert seconds to MM:SS for embedding in transcript text."""
    mins, secs = divmod(int(seconds), 60)
    return f"{mins}:{secs:02d}"


def _extract_video_id(url: str) -> str | None:
    """Return the YouTube video ID from any recognised URL form, or None."""
    parsed = urlparse(url)
    # youtu.be/<id>
    if parsed.hostname in ("youtu.be",):
        vid = parsed.path.lstrip("/").split("/")[0]
        return vid or None
    # youtube.com/watch?v=<id>
    qs = parse_qs(parsed.query)
    if "v" in qs:
        return qs["v"][0] or None
    # youtube.com/embed/<id>
    parts = parsed.path.split("/")
    try:
        idx = parts.index("embed")
        vid = parts[idx + 1] if idx + 1 < len(parts) else ""
        return vid or None
    except ValueError:
        pass
    return None


class YoutubeSkill(BaseSkill):
    meta = SkillMeta(
        name="youtube",
        description="Extract transcripts from YouTube videos via the YouTube caption system",
        extensions=["https://www.youtube.com/", "https://youtu.be/"],
    )

    def __init__(self, provider=None) -> None:
        super().__init__()
        self._provider = provider

    async def _summarise(self, transcript_text: str) -> str:
        limit = 400 if _is_cjk_dominant(transcript_text) else 200
        prompt = _YOUTUBE_SUMMARY_PROMPT.format(
            limit=limit,
            transcript=transcript_text[:6000],
        )
        from synthadoc.providers.base import Message
        resp = await self._provider.complete(
            messages=[Message(role="user", content=prompt)],
            temperature=0.3,
            max_tokens=512,
        )
        return resp.text.strip()

    async def extract(self, source: str) -> ExtractedContent:
        from youtube_transcript_api import (
            YouTubeTranscriptApi,
            NoTranscriptFound,
            VideoUnavailable,
        )

        video_id = _extract_video_id(source)
        if not video_id:
            logger.warning("youtube: could not parse video ID from %s — skipping", source)
            return ExtractedContent(text="", source_path=source, metadata={"url": source})

        api = YouTubeTranscriptApi()
        try:
            fetched = await asyncio.to_thread(api.fetch, video_id)
        except NoTranscriptFound:
            logger.warning(
                "youtube: no captions available for %s — "
                "enable auto-generated captions or choose a different video",
                source,
            )
            return ExtractedContent(
                text="",
                source_path=source,
                metadata={"url": source, "video_id": video_id, "no_transcript": True},
            )
        except VideoUnavailable:
            logger.warning(
                "youtube: video unavailable (private or deleted): %s — skipping", source
            )
            return ExtractedContent(
                text="", source_path=source, metadata={"url": source}
            )

        transcript_text = " ".join(
            f"[{_format_timestamp(snippet.start)}] {snippet.text}" for snippet in fetched
        )

        if self._provider is not None:
            try:
                summary = await self._summarise(transcript_text)
                structured = (
                    f"## Executive Summary\n\n{summary}\n\n"
                    f"## Transcript\n\n{transcript_text}"
                )
                return ExtractedContent(
                    text=structured,
                    source_path=source,
                    metadata={"url": source, "video_id": video_id, "has_summary": True},
                )
            except Exception:
                logger.warning(
                    "youtube: summary LLM call failed for %s — returning raw transcript", source
                )

        return ExtractedContent(
            text=transcript_text,
            source_path=source,
            metadata={"url": source, "video_id": video_id},
        )
