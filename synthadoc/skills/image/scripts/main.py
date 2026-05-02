# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import base64
from pathlib import Path
from synthadoc.skills.base import BaseSkill, ExtractedContent, SkillMeta

_VISION_PROMPT = (
    "Extract all text and key information from this image. "
    "Return plain text only, preserving the structure and content faithfully."
)

_MEDIA_MAP = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "gif": "image/gif",
    "tiff": "image/tiff",
}


class ImageSkill(BaseSkill):
    meta = SkillMeta(name="image",
                     description="Extract text from images using a vision LLM",
                     extensions=[".png", ".jpg", ".jpeg", ".webp", ".gif", ".tiff"])

    def __init__(self, provider=None) -> None:
        super().__init__()
        self._provider = provider

    async def extract(self, source: str) -> ExtractedContent:
        if self._provider is None:
            raise ValueError(
                "ImageSkill requires a vision-capable provider. "
                "Pass provider= when constructing ImageSkill."
            )
        if not getattr(self._provider, "supports_vision", True):
            raise NotImplementedError(
                "Image extraction requires a vision-capable model. "
                "Switch to anthropic (claude-*) or openai (gpt-4o) for image sources."
            )

        data = Path(source).read_bytes()
        suffix = Path(source).suffix.lower().lstrip(".")
        media_type = _MEDIA_MAP.get(suffix, "image/png")
        b64 = base64.b64encode(data).decode()

        from synthadoc.providers.base import Message
        resp = await self._provider.complete(
            messages=[Message(role="user", content=[
                {"type": "image", "source": {
                    "type": "base64", "media_type": media_type, "data": b64,
                }},
                {"type": "text", "text": _VISION_PROMPT},
            ])],
            temperature=0.0,
        )
        return ExtractedContent(
            text=resp.text,
            source_path=source,
            metadata={
                "tokens_input": resp.input_tokens,
                "tokens_output": resp.output_tokens,
            },
        )
