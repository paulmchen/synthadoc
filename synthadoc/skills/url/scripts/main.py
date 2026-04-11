# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import httpx
from bs4 import BeautifulSoup
from synthadoc.skills.base import BaseSkill, ExtractedContent, SkillMeta


class UrlSkill(BaseSkill):
    meta = SkillMeta(name="url", description="Fetch and extract text from web URLs",
                     extensions=["https://", "http://"])

    async def extract(self, source: str) -> ExtractedContent:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            resp = await client.get(source)
            resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        return ExtractedContent(text=soup.get_text(separator="\n", strip=True),
                                source_path=source, metadata={"url": source})
