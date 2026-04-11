# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from pathlib import Path
from synthadoc.skills.base import BaseSkill, ExtractedContent, SkillMeta


class MarkdownSkill(BaseSkill):
    meta = SkillMeta(name="markdown", description="Ingest markdown and plain text files",
                     extensions=[".md", ".txt"])

    async def extract(self, source: str) -> ExtractedContent:
        return ExtractedContent(text=Path(source).read_text(encoding="utf-8"),
                                source_path=source, metadata={})
