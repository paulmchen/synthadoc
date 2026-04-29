# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from synthadoc.skills.base import BaseSkill, ExtractedContent

# Matches all generic intents declared in SKILL.md; colon and leading whitespace optional
_INTENT_RE = re.compile(
    r"^(search\s+for|find\s+on\s+the\s+web|look\s+up|web\s+search|browse):?\s*",
    re.IGNORECASE,
)

# Matches YouTube-specific intent prefixes.  All of these should search YouTube only.
#   "youtube Moore's Law"
#   "youtube video on transistors"
#   "youtube kids: Sesame Street"
#   "search for youtube: history of computing"
#   "search youtube: Moore's Law"
#   "youtube search: lectures on transformers"
_YOUTUBE_INTENT_RE = re.compile(
    r"""^(?:
        search\s+(?:for\s+)?youtube(?:\s+for)?   # search for youtube / search youtube / search youtube for
        | youtube\s+search                         # youtube search
        | youtube(?:\s+(?:video|kids|lecture|talk|channel|for))?  # youtube / youtube video / youtube kids …
    )\s*:?\s*""",
    re.IGNORECASE | re.VERBOSE,
)

# Domains passed to Tavily when a YouTube-specific search is detected
_YOUTUBE_DOMAINS = ["youtube.com", "youtu.be"]

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
    # Wikipedia blocks plain HTTP clients even with a browser User-Agent
    "wikipedia.org",
    # Require institutional/subscription access
    "ieeexplore.ieee.org",
    "dl.acm.org",
    "sciencedirect.com",
    "springer.com",
    "jstor.org",
}


def _load_dynamic_blocked() -> set[str]:
    """Load domains auto-blocked at runtime from .synthadoc/blocked_domains.json."""
    wiki_root = os.environ.get("SYNTHADOC_WIKI_ROOT", "")
    if not wiki_root:
        return set()
    blocked_path = Path(wiki_root) / ".synthadoc" / "blocked_domains.json"
    if not blocked_path.exists():
        return set()
    try:
        return set(json.loads(blocked_path.read_text(encoding="utf-8")))
    except Exception:
        return set()


class WebSearchSkill(BaseSkill):
    async def extract(self, source: str) -> ExtractedContent:
        api_key = os.environ.get("TAVILY_API_KEY", "").strip()
        if not api_key:
            raise EnvironmentError(
                "[ERR-SKILL-004] TAVILY_API_KEY is not set. Get a free key at https://tavily.com "
                "and set it with: export TAVILY_API_KEY=<your-key>"
            )
        max_results = int(
            os.environ.get("SYNTHADOC_WEB_SEARCH_MAX_RESULTS", _DEFAULT_MAX_RESULTS)
        )

        youtube_match = _YOUTUBE_INTENT_RE.match(source)
        if youtube_match:
            query = source[youtube_match.end():].strip() or source
            include_domains: list[str] | None = _YOUTUBE_DOMAINS
        else:
            query = _INTENT_RE.sub("", source).strip() or source
            include_domains = None

        from synthadoc.skills.web_search.scripts.fetcher import search_tavily
        response = await search_tavily(
            query, max_results=max_results, api_key=api_key,
            include_domains=include_domains,
        )

        all_blocked = _BLOCKED_DOMAINS | _load_dynamic_blocked()

        def _allowed(url: str) -> bool:
            host = urlparse(url).hostname or ""
            return not any(host == d or host.endswith("." + d) for d in all_blocked)

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
