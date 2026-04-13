# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import tempfile
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
            content_type = resp.headers.get("content-type", "")
            is_pdf = "application/pdf" in content_type or source.lower().endswith(".pdf")
            if is_pdf:
                return self._extract_pdf_response(resp.content, source)
            html = resp.text

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        return ExtractedContent(text=soup.get_text(separator="\n", strip=True),
                                source_path=source, metadata={"url": source})

    def _extract_pdf_response(self, content: bytes, source: str) -> ExtractedContent:
        """Write PDF bytes to a temp file and extract text via pypdf."""
        import pypdf
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            parts = []
            with open(tmp_path, "rb") as f:
                reader = pypdf.PdfReader(f)
                num_pages = len(reader.pages)
                for page in reader.pages:
                    t = page.extract_text()
                    if t:
                        parts.append(t)
            text = "\n".join(parts)
        finally:
            import os
            os.unlink(tmp_path)
        return ExtractedContent(text=text, source_path=source,
                                metadata={"url": source, "pages": num_pages})
