# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

from synthadoc.providers.base import LLMProvider, Message

logger = logging.getLogger(__name__)

SCAFFOLD_MARKER = "<!-- synthadoc:scaffold -->"

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)

_SYSTEM_PROMPT = (
    "You are a knowledge management assistant helping to set up a domain-specific wiki. "
    "Return ONLY valid JSON — no markdown fences, no explanation."
)

_SCAFFOLD_PROMPT = """\
Set up a knowledge wiki for the domain: {domain}

{protected_section}Generate a scaffold with 5-8 categories appropriate for this domain.

Return ONLY valid JSON:
{{
  "categories": [
    {{
      "heading": "Category Name",
      "description": "what pages go in this category",
      "slugs": ["slug-one", "slug-two"]
    }},
    ...
  ],
  "agents_guidelines": "2-4 bullet points of domain-specific ingest and query guidelines (plain text, not markdown list syntax)",
  "purpose_include": "one sentence: what topics belong in this wiki",
  "purpose_exclude": "one sentence: what topics to exclude",
  "dashboard_intro": "one sentence describing what this wiki tracks"
}}

The "slugs" array must contain the kebab-case page slugs that belong in each category.
{slugs_instruction}If a category has no known pages yet, use an empty array.
"""

_INDEX_FRONTMATTER = """\
---
title: Index
tags: [index]
status: active
confidence: high
created: '{created}'
sources: []
---

"""

_AGENTS_MD_TEMPLATE = """\
# AGENTS.md — {domain} Wiki

## Purpose
This wiki captures knowledge about: {domain}.

## Ingest Guidelines
{guidelines}

## Query Guidelines
- Answer using only wiki content
- Always cite sources using `[[page-name]]` link syntax
"""

_PURPOSE_MD_TEMPLATE = """\
# Wiki Purpose

This wiki covers: {domain}.

Include: {include}
Exclude: {exclude}
"""


def preserve_user_zone(existing_content: str, new_scaffold_content: str) -> str:
    """Return index.md content preserving the user zone above SCAFFOLD_MARKER.

    If the marker is absent, returns new_scaffold_content unchanged (full rewrite).
    """
    if SCAFFOLD_MARKER not in existing_content:
        return new_scaffold_content
    user_zone = existing_content.split(SCAFFOLD_MARKER)[0].rstrip()
    return f"{user_zone}\n\n{SCAFFOLD_MARKER}\n\n{new_scaffold_content}"


@dataclass
class ScaffoldResult:
    index_md: str
    agents_md: str
    purpose_md: str
    dashboard_intro: str


class ScaffoldAgent:
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    async def scaffold(
        self,
        domain: str,
        protected_slugs: Optional[list[str]] = None,
    ) -> ScaffoldResult:
        protected_section = ""
        slugs_instruction = ""
        if protected_slugs:
            slugs_list = ", ".join(protected_slugs)
            protected_section = (
                f"IMPORTANT: The following page slugs already exist in the wiki: {slugs_list}\n\n"
            )
            slugs_instruction = (
                "Assign each of the existing slugs listed above into the most appropriate "
                'category\'s "slugs" array. Every protected slug must appear in exactly one category. '
            )

        prompt = _SCAFFOLD_PROMPT.format(
            domain=domain,
            protected_section=protected_section,
            slugs_instruction=slugs_instruction,
        )

        resp = await self._provider.complete(
            messages=[Message(role="user", content=prompt)],
            system=_SYSTEM_PROMPT,
            temperature=0.3,
            max_tokens=2048,
        )

        raw = resp.text.strip()
        # Strip markdown fences if present
        m = _FENCE_RE.search(raw)
        if m:
            raw = m.group(1)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"ScaffoldAgent: LLM returned unparseable scaffold JSON: {exc}"
            ) from exc

        return ScaffoldResult(
            index_md=self._build_index_md(domain, data),
            agents_md=self._build_agents_md(domain, data),
            purpose_md=self._build_purpose_md(domain, data),
            dashboard_intro=data.get("dashboard_intro", f"A wiki tracking {domain} knowledge."),
        )

    def _build_index_md(self, domain: str, data: dict) -> str:
        today = date.today().isoformat()
        lines = [_INDEX_FRONTMATTER.format(created=today)]
        lines.append(f"# {domain} — Index\n")
        for cat in data.get("categories", []):
            heading = cat.get("heading", "General")
            desc = cat.get("description", "")
            slugs = cat.get("slugs", [])
            lines.append(f"\n## {heading}")
            if desc:
                lines.append(f"*{desc}*\n")
            for slug in slugs:
                if slug:
                    lines.append(f"- [[{slug}]]")
            if slugs:
                lines.append("")
        lines.append("")
        return "\n".join(lines)

    def _build_agents_md(self, domain: str, data: dict) -> str:
        raw_guidelines = data.get("agents_guidelines", "Summarize key claims.")
        # Normalise to bullet list
        bullets = []
        for line in raw_guidelines.splitlines():
            line = line.strip().lstrip("-•* ")
            if line:
                bullets.append(f"- {line}")
        guidelines = "\n".join(bullets) if bullets else f"- {raw_guidelines}"
        return _AGENTS_MD_TEMPLATE.format(domain=domain, guidelines=guidelines)

    def _build_purpose_md(self, domain: str, data: dict) -> str:
        return _PURPOSE_MD_TEMPLATE.format(
            domain=domain,
            include=data.get("purpose_include", f"Topics directly related to {domain}."),
            exclude=data.get("purpose_exclude", "Unrelated domains."),
        )
