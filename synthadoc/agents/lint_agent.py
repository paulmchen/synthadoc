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


class LintAgent:
    def __init__(self, provider: LLMProvider, store: WikiStorage,
                 log_writer: LogWriter, confidence_threshold: float = 0.85) -> None:
        self._provider = provider
        self._store = store
        self._log = log_writer
        self._threshold = confidence_threshold

    def _find_orphans(self, slugs: list[str]) -> list[str]:
        referenced: set[str] = set()
        for slug in slugs:
            page = self._store.read_page(slug)
            if page:
                for link in _WIKILINK_RE.findall(page.content):
                    # Strip alias (e.g. [[slug|Display Text]]) before normalising
                    slug_part = link.split("|")[0].strip()
                    referenced.add(slug_part.lower().replace(" ", "-"))
        return [s for s in slugs if s not in referenced
                and s not in ("index", "dashboard", "log", "purpose")]

    async def lint(self, scope: str = "all", auto_resolve: bool = False) -> LintReport:
        report = LintReport()
        slugs = self._store.list_pages()

        if scope in ("all", "contradictions"):
            for slug in slugs:
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
