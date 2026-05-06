# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime

from synthadoc.providers.base import LLMProvider
from synthadoc.storage.search import HybridSearch
from synthadoc.storage.wiki import WikiStorage
from synthadoc.agents.query_agent import QueryAgent

_WORDS_PER_TOKEN = 0.75  # rough approximation


def _estimate_tokens(text: str) -> int:
    return max(1, int(len(text.split()) / _WORDS_PER_TOKEN))


@dataclass
class ContextPage:
    slug: str
    relevance: float
    excerpt: str
    source: str
    confidence: str
    tags: list[str]
    estimated_tokens: int


@dataclass
class ContextPack:
    goal: str
    token_budget: int
    tokens_used: int
    pages: list[ContextPage] = field(default_factory=list)
    omitted: list[ContextPage] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [
            f"# Context Pack: {self.goal}",
            f"Generated: {datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}",
            f"Token budget: {self.token_budget} | Used: {self.tokens_used}"
            + (f" | Omitted: {len(self.omitted)} pages (budget exceeded)" if self.omitted else ""),
            "", "---", "",
        ]
        for p in self.pages:
            lines += [
                f"## [[{p.slug}]] — relevance: {p.relevance:.2f}",
                f"> {p.excerpt}",
                f"Source: `{p.source}` | Confidence: {p.confidence}"
                + (f" | Tags: {', '.join(p.tags)}" if p.tags else ""),
                "",
            ]
        if self.omitted:
            lines += ["---", "", "## Omitted — token budget exceeded"]
            for p in self.omitted:
                lines.append(f"- [[{p.slug}]] — ~{p.estimated_tokens} tokens")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "token_budget": self.token_budget,
            "tokens_used": self.tokens_used,
            "pages": [
                {
                    "slug": p.slug, "relevance": p.relevance, "excerpt": p.excerpt,
                    "source": p.source, "confidence": p.confidence, "tags": p.tags,
                    "estimated_tokens": p.estimated_tokens,
                }
                for p in self.pages
            ],
            "omitted": [
                {"slug": p.slug, "estimated_tokens": p.estimated_tokens}
                for p in self.omitted
            ],
        }


class ContextAgent:
    def __init__(self, provider: LLMProvider, store: WikiStorage,
                 search: HybridSearch, token_budget: int = 4000,
                 top_n: int = 8) -> None:
        self._qa = QueryAgent(provider=provider, store=store, search=search, top_n=top_n)
        self._store = store
        self._search = search
        self._token_budget = token_budget
        self._top_n = top_n

    async def build(self, goal: str, token_budget: int | None = None) -> ContextPack:
        budget = token_budget if token_budget is not None else self._token_budget
        sub_questions = await self._qa.decompose(goal)
        results_per_q = await asyncio.gather(*[
            self._search.hybrid_search(q.lower().split(), top_n=self._top_n)
            for q in sub_questions
        ])

        # Merge — best score per slug
        best: dict = {}
        for results in results_per_q:
            for r in results:
                if r.slug not in best or r.score > best[r.slug].score:
                    best[r.slug] = r
        ranked = sorted(best.values(), key=lambda r: r.score, reverse=True)

        pages, omitted, used = [], [], 0
        for r in ranked:
            # Get page content from store (SearchResult doesn't carry full content)
            page = self._store.read_page(r.slug)
            content = page.content if page else r.snippet
            excerpt = " ".join(content.split()[:120])
            tokens = _estimate_tokens(excerpt)
            cp = ContextPage(
                slug=r.slug,
                relevance=round(r.score, 2),
                excerpt=excerpt,
                source=f"wiki/{r.slug}.md",
                confidence=page.confidence if page else "medium",
                tags=list(page.tags or []) if page else [],
                estimated_tokens=tokens,
            )
            if used + tokens <= budget:
                pages.append(cp)
                used += tokens
            else:
                omitted.append(cp)

        return ContextPack(goal=goal, token_budget=budget,
                           tokens_used=used, pages=pages, omitted=omitted)
