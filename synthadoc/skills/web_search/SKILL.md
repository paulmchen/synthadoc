---
name: web_search
version: "0.1"
description: Search the web and ingest results as wiki pages
entry:
  script: scripts/main.py
  class: WebSearchSkill
triggers:
  extensions: []
  intents:
    - "search for"
    - "find on the web"
    - "look up"
    - "web search"
    - "browse"
requires:
  - httpx
  - beautifulsoup4
author: axoviq.com
license: AGPL-3.0-or-later
---

# Web Search Skill

Accepts a natural language query, calls a configured search API, fetches
the top results, and returns extracted text to the IngestAgent for wiki
compilation.

## Status

**v1 stub — `extract()` raises `NotImplementedError`.** Full implementation
is scheduled for v2.

## When this skill is used

- Source string contains: `search for`, `find on the web`, `look up`,
  `web search`, `browse`
- No file extension — purely intent-driven

## Scripts

- `scripts/main.py` — `WebSearchSkill` (stub)
- `scripts/fetcher.py` — HTTP + HTML cleaning helper (v2)

## Assets

- `assets/search-providers.json` — search API endpoint configuration (v2)
