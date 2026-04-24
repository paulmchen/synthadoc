# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import re
from dataclasses import dataclass, field

from synthadoc.providers.base import LLMProvider, Message
from synthadoc.storage.log import LogWriter
from synthadoc.storage.wiki import WikiStorage


@dataclass
class LintReport:
    contradictions_found: int = 0
    contradictions_resolved: int = 0
    orphan_slugs: list[str] = field(default_factory=list)
    tokens_used: int = 0


_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")

# Auto-generated pages excluded from both reference-counting and orphan reporting.
# A page linked only from overview/index is still an orphan in the human graph.
LINT_SKIP_SLUGS: frozenset[str] = frozenset(
    {"index", "log", "dashboard", "purpose", "overview"}
)


def find_orphan_slugs(
    page_texts: dict[str, str],
    skip: frozenset[str] = LINT_SKIP_SLUGS,
) -> list[str]:
    """Return slugs with no inbound [[wikilinks]] from other non-skip pages.

    page_texts maps slug → page body text (frontmatter must be stripped by caller).
    Links from skip pages (overview, index, …) and self-links are not counted.
    """
    referenced: set[str] = set()
    for slug, text in page_texts.items():
        if slug in skip:
            continue
        for link in _WIKILINK_RE.findall(text):
            slug_part = link.split("|")[0].strip()
            target = slug_part.lower().replace(" ", "-")
            if target != slug:  # self-links don't count as inbound references
                referenced.add(target)
    return [s for s in page_texts if s not in referenced and s not in skip]


class LintAgent:
    def __init__(self, provider: LLMProvider, store: WikiStorage,
                 log_writer: LogWriter, confidence_threshold: float = 0.85) -> None:
        self._provider = provider
        self._store = store
        self._log = log_writer
        self._threshold = confidence_threshold

    def _find_orphans(self, slugs: list[str]) -> list[str]:
        page_texts = {
            slug: (self._store.read_page(slug).content
                   if self._store.read_page(slug) else "")
            for slug in slugs
        }
        return find_orphan_slugs(page_texts)

    async def lint(self, scope: str = "all", auto_resolve: bool = False) -> LintReport:
        report = LintReport()
        slugs = self._store.list_pages()

        if scope in ("all", "contradictions"):
            for slug in slugs:
                if slug in LINT_SKIP_SLUGS:
                    continue
                page = self._store.read_page(slug)
                if page and page.status == "contradicted":
                    report.contradictions_found += 1
                    if auto_resolve:
                        resp = await self._provider.complete(
                            messages=[Message(role="user",
                                content=f"Propose resolution:\n{page.content[:500]}")],
                            temperature=0.0,
                        )
                        report.tokens_used += resp.total_tokens
                        page.status = "active"
                        page.content += f"\n\n**Resolution:** {resp.text}"
                        self._store.write_page(slug, page)
                        report.contradictions_resolved += 1

        if scope in ("all", "orphans"):
            report.orphan_slugs = self._find_orphans(slugs)
            orphan_set = set(report.orphan_slugs)
            for slug in slugs:
                page = self._store.read_page(slug)
                if page and page.orphan != (slug in orphan_set):
                    page.orphan = slug in orphan_set
                    self._store.write_page(slug, page)

        self._log.log_lint(resolved=report.contradictions_resolved,
                           flagged=report.contradictions_found - report.contradictions_resolved,
                           orphans=len(report.orphan_slugs))
        return report
