# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from synthadoc.skills.base import BaseSkill, ExtractedContent, SkillMeta
from synthadoc.errors import DomainBlockedException


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

# HTTP status codes that indicate bot/access blocking (not transient errors)
_BLOCKED_STATUSES = {403, 401, 429}


class UrlSkill(BaseSkill):
    meta = SkillMeta(name="url", description="Fetch and extract text from web URLs",
                     extensions=["https://", "http://"])

    async def extract(self, source: str) -> ExtractedContent:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30, headers=_HEADERS) as client:
            resp = await client.get(source)
            if resp.status_code in _BLOCKED_STATUSES:
                domain = urlparse(source).hostname or source
                raise DomainBlockedException(
                    domain=domain, url=source, status_code=resp.status_code
                )
            resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        return ExtractedContent(text=soup.get_text(separator="\n", strip=True),
                                source_path=source, metadata={"url": source})
