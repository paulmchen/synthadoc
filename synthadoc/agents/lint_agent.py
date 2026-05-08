# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import re
from dataclasses import dataclass, field

from synthadoc.providers.base import LLMProvider, Message
from synthadoc.storage.log import AuditDB, LogWriter
from synthadoc.storage.wiki import WikiStorage


@dataclass
class LintReport:
    contradictions_found: int = 0
    contradictions_resolved: int = 0
    contradictions_unresolved: list[dict] = field(default_factory=list)  # [{slug, reason}]
    orphan_slugs: list[str] = field(default_factory=list)
    dangling_links_removed: int = 0
    tokens_used: int = 0


_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")

# Auto-generated / directory pages whose outbound links must NOT count as real
# references.  A page linked only from index/overview/dashboard is still an
# orphan in the content graph — it is not integrated into the knowledge network.
LINT_SKIP_SOURCE_SLUGS: frozenset[str] = frozenset(
    {"index", "overview", "log", "dashboard"}
)

# Pages never reported as orphans (root / auto-generated pages).
LINT_SKIP_SLUGS: frozenset[str] = frozenset(
    {"index", "log", "dashboard", "purpose", "overview"}
)


# Matches a list item whose first significant content is a single wikilink,
# e.g. "- [[some-slug]] — description" or "* [[slug]]"
_LIST_LINK_RE = re.compile(r"^\s*[-*+]\s+\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


def _fix_dangling_wikilinks(content: str, existing_slugs: set[str]) -> str:
    """Remove or unlink [[slug]] references whose target page no longer exists.

    List items whose entire content is a dangling link are dropped.
    Inline dangling links are replaced with just their display text.
    """
    lines = content.splitlines(keepends=True)
    result: list[str] = []
    for line in lines:
        stripped = line.rstrip("\n\r")
        m = _LIST_LINK_RE.match(stripped)
        if m:
            slug_part = m.group(1).strip().lower().replace(" ", "-")
            if slug_part not in existing_slugs:
                continue  # drop the whole list-item line

        def _unlink(match: re.Match) -> str:
            inner = match.group(1)
            parts = inner.split("|", 1)
            slug_key = parts[0].strip().lower().replace(" ", "-")
            display = parts[1].strip() if len(parts) > 1 else parts[0].strip()
            return display if slug_key not in existing_slugs else match.group(0)

        line = _WIKILINK_RE.sub(_unlink, line)
        result.append(line)
    return "".join(result)


def find_orphan_slugs(
    page_texts: dict[str, str],
    skip: frozenset[str] = LINT_SKIP_SLUGS,
    skip_source: frozenset[str] = LINT_SKIP_SOURCE_SLUGS,
) -> list[str]:
    """Return slugs with no inbound [[wikilinks]] from other content pages.

    page_texts maps slug → page body text (frontmatter must be stripped by caller).
    Links from skip_source pages (index, overview, dashboard, log) and self-links
    are not counted — only connections between content pages rescue from orphan.
    """
    referenced: set[str] = set()
    for slug, text in page_texts.items():
        if slug in skip_source:
            continue
        for link in _WIKILINK_RE.findall(text):
            slug_part = link.split("|")[0].strip()
            target = slug_part.lower().replace(" ", "-")
            if target != slug:  # self-links don't count as inbound references
                referenced.add(target)
    return [s for s in page_texts if s not in referenced and s not in skip]


class LintAgent:
    def __init__(self, provider: LLMProvider, store: WikiStorage,
                 log_writer: LogWriter, confidence_threshold: float = 0.85,
                 audit_db: AuditDB | None = None) -> None:
        self._provider = provider
        self._store = store
        self._log = log_writer
        self._threshold = confidence_threshold
        self._audit = audit_db

    def _find_orphans(self, slugs: list[str]) -> list[str]:
        page_texts = {}
        for slug in slugs:
            page = self._store.read_page(slug)
            page_texts[slug] = page.content if page else ""
        return find_orphan_slugs(page_texts)

    def _clean_dangling_links(self, slugs: list[str]) -> int:
        slug_set = set(slugs)
        fixed = 0
        for slug in slugs:
            page = self._store.read_page(slug)
            if not page:
                continue
            new_content = _fix_dangling_wikilinks(page.content, slug_set)
            if new_content != page.content:
                page.content = new_content
                self._store.write_page(slug, page)
                fixed += 1
        return fixed

    async def lint(self, scope: str = "all", auto_resolve: bool = False,
                   job_id: str = "system") -> LintReport:
        report = LintReport()
        slugs = self._store.list_pages()

        if scope in ("all", "contradictions"):
            for slug in slugs:
                if slug in LINT_SKIP_SLUGS:
                    continue
                page = self._store.read_page(slug)
                if page and page.status == "contradicted":
                    report.contradictions_found += 1
                    if self._audit:
                        await self._audit.record_audit_event(
                            job_id, "contradiction_found", {"slug": slug})
                    if auto_resolve:
                        note = page.contradiction_note or ""
                        prompt = (
                            "A wiki page has been flagged as contradicted by a new source.\n"
                            "Your job is to produce an updated page that is accurate given both sources.\n"
                            "Resolution strategy: rewrite the disputed claim to represent BOTH perspectives "
                            "accurately — do NOT pick a winner. If one source says X and another says Y, "
                            "present both with appropriate hedging (e.g. 'widely regarded as…, though some "
                            "historians argue…').\n"
                            "Only mark resolvable=false if the page itself should not exist, or the conflict "
                            "cannot be addressed through editorial nuance (e.g. the entire page is a fabrication).\n"
                            "Return ONLY valid JSON, no markdown fences:\n"
                            '{"resolvable": true|false, "reason": "one sentence explaining why or why not", '
                            '"resolution": "complete rewritten page content if resolvable, else empty string"}\n\n'
                            f"Contradiction note: {note}\n\n"
                            f"Current page content:\n{page.content[:2000]}"
                        )
                        resp = await self._provider.complete(
                            messages=[Message(role="user", content=prompt)],
                            temperature=0.0,
                        )
                        report.tokens_used += resp.total_tokens
                        try:
                            import json as _json
                            raw = resp.text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
                            decision = _json.loads(raw)
                        except Exception:
                            decision = {"resolvable": False, "reason": "auto-resolve returned unparseable output", "resolution": ""}
                        if decision.get("resolvable"):
                            page.status = "active"
                            page.contradiction_note = None
                            page.unresolved_note = None
                            resolution = decision.get("resolution", "").strip()
                            if resolution:
                                page.content = resolution
                            else:
                                page.content += f"\n\n**Auto-resolved:** {decision.get('reason', '')}"
                            self._store.write_page(slug, page)
                            report.contradictions_resolved += 1
                            if self._audit:
                                await self._audit.record_audit_event(
                                    job_id, "auto_resolved", {"slug": slug})
                        else:
                            reason = decision.get("reason", "Could not determine a confident resolution.")
                            page.unresolved_note = reason
                            self._store.write_page(slug, page)
                            report.contradictions_unresolved.append({"slug": slug, "reason": reason})
                            if self._audit:
                                await self._audit.record_audit_event(
                                    job_id, "auto_resolve_failed", {"slug": slug, "reason": reason})

        if scope in ("all", "orphans"):
            report.dangling_links_removed = self._clean_dangling_links(slugs)
            slugs = self._store.list_pages()  # re-read after deletions
            report.orphan_slugs = self._find_orphans(slugs)
            orphan_set = set(report.orphan_slugs)
            for slug in slugs:
                page = self._store.read_page(slug)
                if page and page.orphan != (slug in orphan_set):
                    page.orphan = slug in orphan_set
                    self._store.write_page(slug, page)

        self._log.log_lint(resolved=report.contradictions_resolved,
                           flagged=report.contradictions_found - report.contradictions_resolved,
                           orphans=len(report.orphan_slugs),
                           dangling_removed=report.dangling_links_removed)
        return report
