# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import base64
from pathlib import Path
from synthadoc.skills.base import BaseSkill, ExtractedContent, SkillMeta


class ImageSkill(BaseSkill):
    meta = SkillMeta(name="image",
                     description="Extract content from images via vision-capable LLMs",
                     extensions=[".png", ".jpg", ".jpeg", ".webp", ".gif", ".tiff"])

    async def extract(self, source: str) -> ExtractedContent:
        data = Path(source).read_bytes()
        suffix = Path(source).suffix.lower().lstrip(".")
        media_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                     "webp": "image/webp", "gif": "image/gif", "tiff": "image/tiff"}
        return ExtractedContent(
            text="",  # populated by IngestAgent via vision LLM call
            source_path=source,
            metadata={"base64": base64.b64encode(data).decode(),
                      "media_type": media_map.get(suffix, "image/png"), "is_image": True},
        )
