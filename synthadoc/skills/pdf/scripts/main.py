# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import logging

import pypdf

from synthadoc.skills.base import BaseSkill, ExtractedContent, SkillMeta

logger = logging.getLogger(__name__)

# pypdf logs benign structural warnings (e.g. incorrect startxref pointer) at WARNING
# level for many real-world PDFs. Suppress them so they don't pollute the console.
logging.getLogger("pypdf").setLevel(logging.ERROR)

# If pypdf extracts fewer than this many characters per page on average,
# the PDF likely uses CJK fonts whose ToUnicode CMaps pypdf cannot decode.
# In that case we fall back to pdfminer.six which has better CJK support.
_MIN_CHARS_PER_PAGE = 50


class PdfSkill(BaseSkill):
    meta = SkillMeta(name="pdf", description="Extract text from PDF files", extensions=[".pdf"])

    async def extract(self, source: str) -> ExtractedContent:
        text, num_pages = self._extract_pypdf(source)

        # Low yield → likely CJK fonts that pypdf cannot decode; try pdfminer fallback
        if num_pages > 0 and len(text.strip()) < num_pages * _MIN_CHARS_PER_PAGE:
            logger.debug(
                "pypdf yielded %d chars for %d page(s) in %s — trying pdfminer fallback",
                len(text.strip()), num_pages, source,
            )
            fallback = self._extract_pdfminer(source)
            if len(fallback.strip()) > len(text.strip()):
                text = fallback

        return ExtractedContent(text=text, source_path=source,
                                metadata={"pages": num_pages})

    def _extract_pypdf(self, source: str) -> tuple[str, int]:
        try:
            parts = []
            with open(source, "rb") as f:
                reader = pypdf.PdfReader(f)
                num_pages = len(reader.pages)
                for page in reader.pages:
                    t = page.extract_text()
                    if t:
                        parts.append(t)
            return "\n".join(parts), num_pages
        except (FileNotFoundError, IsADirectoryError):
            raise
        except Exception as exc:
            raise ValueError(
                f"Cannot read '{source}' as a PDF file: {exc}. "
                "Ensure the file is a valid PDF document."
            ) from exc

    def _extract_pdfminer(self, source: str) -> str:
        try:
            from pdfminer.high_level import extract_text
            return extract_text(source) or ""
        except Exception as exc:
            logger.debug("pdfminer fallback failed for %s: %s", source, exc)
            return ""
