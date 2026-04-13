# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import os
from synthadoc.skills.base import BaseSkill, ExtractedContent

import re
from urllib.parse import urlparse

# Matches all intents declared in SKILL.md; colon and leading whitespace optional
_INTENT_RE = re.compile(
    r"^(search\s+for|find\s+on\s+the\s+web|look\s+up|web\s+search|browse):?\s*",
    re.IGNORECASE,
)
_DEFAULT_MAX_RESULTS = 20

# Domains that block automated HTTP clients (Cloudflare, login walls, etc.).
# URLs from these domains are skipped to prevent dead ingest jobs.
_BLOCKED_DOMAINS = {
    # Require JavaScript/login — can't be fetched by a plain HTTP client
    "quora.com",
    "medium.com",
    "reddit.com",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "linkedin.com",
    "tiktok.com",
    # Require institutional/subscription access
    "ieeexplore.ieee.org",
    "dl.acm.org",
    "sciencedirect.com",
    "springer.com",
    "jstor.org",
}


class WebSearchSkill(BaseSkill):
    async def extract(self, source: str) -> ExtractedContent:
        api_key = os.environ.get("TAVILY_API_KEY", "").strip()
        if not api_key:
            raise EnvironmentError(
                "[SKILL-004] TAVILY_API_KEY is not set. Get a free key at https://tavily.com "
                "and set it with: export TAVILY_API_KEY=<your-key>"
            )
        max_results = int(
            os.environ.get("SYNTHADOC_WEB_SEARCH_MAX_RESULTS", _DEFAULT_MAX_RESULTS)
        )
        query = _INTENT_RE.sub("", source).strip() or source

        from synthadoc.skills.web_search.scripts.fetcher import search_tavily
        response = await search_tavily(query, max_results=max_results, api_key=api_key)

        def _allowed(url: str) -> bool:
            try:
                host = urlparse(url).hostname or ""
                return not any(
                    host == d or host.endswith("." + d) for d in _BLOCKED_DOMAINS
                )
            except Exception:
                return True

        child_sources = [
            r["url"] for r in response.get("results", [])
            if r.get("url") and _allowed(r["url"])
        ]
        return ExtractedContent(
            text="",
            source_path=source,
            metadata={
                "child_sources": child_sources,
                "query": query,
                "results_count": len(child_sources),
            },
        )
