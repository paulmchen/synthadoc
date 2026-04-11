# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from synthadoc.agents.skill_agent import SkillAgent
from synthadoc.core.cache import CacheManager, make_cache_key
from synthadoc.providers.base import LLMProvider, Message
from synthadoc.storage.log import AuditDB, LogWriter
from synthadoc.storage.search import HybridSearch
from synthadoc.storage.wiki import WikiPage, WikiStorage

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    source: str
    pages_created: list[str] = field(default_factory=list)
    pages_updated: list[str] = field(default_factory=list)
    pages_flagged: list[str] = field(default_factory=list)
    tokens_used: int = 0
    cost_usd: float = 0.0
    cache_hits: int = 0
    skipped: bool = False
    skip_reason: str = ""


_ENTITY_PROMPT = (
    "Extract key entities, concepts, and tags from the text below.\n"
    "Return ONLY valid JSON: {\"entities\": [...], \"concepts\": [...], \"tags\": [...]}\n"
    "Keep each list under 10 items.\n\n"
)

_DECISION_PROMPT = (
    "You maintain a knowledge wiki. Decide how to handle a new source document.\n"
    "Return ONLY valid JSON - no markdown fences, no explanation.\n\n"
    "First write a 'reasoning' field explaining your decision, then set 'action'.\n\n"
    "Decision rules (apply in this order):\n\n"
    "RULE 1 — FLAG: If the new source DISPUTES or ARGUES AGAINST a factual claim in an existing page,\n"
    "use action='flag'. This includes academic debates, alternative historical interpretations,\n"
    "or sources that explicitly say an existing claim is wrong or a myth.\n"
    "Example: page says 'A-0 was the first compiler' + source says 'A-0 was a loader, not a compiler'\n"
    "-> action='flag', target=the slug of the page whose claim is disputed\n\n"
    "RULE 2 — UPDATE: If the source adds new information about a subject ALREADY covered by an existing page,\n"
    "and there is no factual dispute, use action='update'.\n"
    "-> action='update', target=slug of page to extend, update_content=new ## section(s) to append\n\n"
    "RULE 3 — CREATE: ONLY if the source covers a subject not in any existing page.\n"
    "-> action='create', new_slug=snake_case_slug\n\n"
    'Return: {{"reasoning":"...","action":"...","target":"","new_slug":"","update_content":""}}\n\n'
    "Existing wiki pages (top matches):\n{pages}\n\n"
    "New source:\n{summary}\n\n"
    "Detected entities: {entities}"
)

_VISION_PROMPT = (
    "Extract all text and key information from this image. "
    "Return plain text only, preserving the structure and content faithfully."
)


def _parse_json_response(text: str) -> dict:
    """Parse a JSON object from an LLM response, handling markdown code fences."""
    text = text.strip()
    # Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Strip markdown code block: ```json ... ``` or ``` ... ```
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Find first {...} in the response
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {}


def _slugify(title: str) -> str:
    # Decompose accented characters (é → e + combining accent) so they map to ASCII
    normalized = unicodedata.normalize("NFKD", title)
    # Keep ASCII alphanumeric and CJK character blocks (valid Obsidian filename chars)
    slug = re.sub(
        r"[^a-z0-9\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]+",
        "-",
        normalized.lower(),
    ).strip("-")
    # Fallback: if title was entirely symbols with no slug-able chars, use a content hash
    return slug or "page-" + hashlib.md5(title.encode()).hexdigest()[:8]


class IngestAgent:
    def __init__(self, provider: LLMProvider, store: WikiStorage, search: HybridSearch,
                 log_writer: LogWriter, audit_db: AuditDB, cache: CacheManager,
                 max_pages: int = 15, wiki_root: Optional[Path] = None) -> None:
        self._provider = provider
        self._store = store
        self._search = search
        self._log = log_writer
        self._audit = audit_db
        self._cache = cache
        self._max_pages = max_pages
        self._wiki_root = Path(wiki_root) if wiki_root is not None else None
        self._skill_agent = SkillAgent()

    def _hash(self, path: str) -> tuple[str, int]:
        data = Path(path).read_bytes()
        return hashlib.sha256(data).hexdigest(), len(data)

    def _needs_file_check(self, source: str) -> bool:
        """Return True when source must exist as a local file before ingestion.

        URL sources (http/https) and intent-matched sources are remote/virtual
        and must bypass the file-system existence check.
        """
        s = source.lower()
        if s.startswith(("http://", "https://")):
            return False
        try:
            meta = self._skill_agent.detect_skill(source)
            if any(intent in s for intent in meta.triggers.intents):
                return False
        except Exception:
            pass
        return True

    async def ingest(self, source: str, force: bool = False, bust_cache: bool = False) -> IngestResult:
        result = IngestResult(source=source)

        if self._needs_file_check(source):
            p = Path(source).resolve()

            # Security: reject sources outside wiki_root
            if self._wiki_root is not None:
                root_resolved = self._wiki_root.resolve()
                try:
                    p.relative_to(root_resolved)
                except ValueError:
                    raise PermissionError(
                        f"Source {p} is outside wiki root {root_resolved}"
                    )

            if not p.exists():
                raise FileNotFoundError(f"Source not found: {source}")
            if p.stat().st_size == 0:
                raise ValueError(f"Source file is empty: {source}")

            # Dedup: hash + size (file sources only)
            src_hash, src_size = self._hash(str(p))

            # Check for hash collision (same hash, different size)
            if not force:
                existing = await self._audit.find_by_hash_only(src_hash)
                if existing and existing["size"] != src_size:
                    logger.warning(
                        "Hash collision detected: hash=%s matches existing record but size differs "
                        "(existing=%d, current=%d). Treating as new source.",
                        src_hash, existing["size"], src_size
                    )
                elif await self._audit.find_by_hash(src_hash, src_size):
                    result.skipped = True
                    result.skip_reason = "already ingested"
                    return result

        extracted = await self._skill_agent.extract(source)

        # Pass 0: Vision extraction for image files
        if extracted.metadata.get("is_image"):
            b64 = extracted.metadata.get("base64", "")
            media_type = extracted.metadata.get("media_type", "image/png")
            vision_resp = await self._provider.complete(
                messages=[Message(role="user", content=[
                    {"type": "image", "source": {
                        "type": "base64", "media_type": media_type, "data": b64,
                    }},
                    {"type": "text", "text": _VISION_PROMPT},
                ])],
                temperature=0.0,
            )
            result.tokens_used += vision_resp.total_tokens
            text = vision_resp.text[:8000]
        else:
            text = extracted.text[:8000]

        # Pass 1: entity extraction (cached by full-content hash)
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        ck = make_cache_key("extract-entities", {"text_hash": text_hash})
        cached = None if bust_cache else await self._cache.get(ck)
        if cached:
            result.cache_hits += 1
            entity_data = cached
        else:
            resp = await self._provider.complete(
                messages=[Message(role="user", content=f"{_ENTITY_PROMPT}{text[:2000]}")],
                temperature=0.0,
            )
            result.tokens_used += resp.total_tokens
            entity_data = _parse_json_response(resp.text)
            await self._cache.set(ck, entity_data)

        entities = entity_data.get("entities", [])
        tags = entity_data.get("tags", [])

        # Fallback: if LLM entity extraction returned nothing, extract key phrases
        # directly from the source text so BM25 always has meaningful search terms.
        if not entities:
            # English: capitalized noun phrases
            english = re.findall(r'\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\b', text[:2000])
            # CJK: consecutive CJK characters as candidate terms (2–6 chars)
            cjk = re.findall(
                r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]{2,6}',
                text[:2000],
            )
            entities = list(dict.fromkeys(english + cjk))[:12]
            logger.debug("Entity extraction returned empty; using text-extracted phrases: %s", entities)

        # Pass 2: hybrid search
        candidates = self._search.bm25_search(entities + tags, top_n=self._max_pages)

        # Build page context: top 5 candidates with content snippets
        pages_ctx = []
        for r in candidates[:5]:
            page = self._store.read_page(r.slug)
            if page:
                snippet = page.content[:600].replace("\n", " ")
                pages_ctx.append(f"[{r.slug}]: {snippet}")
        pages_str = "\n".join(pages_ctx) or "none"

        # Pass 3: decision (cached by text hash + candidate slugs)
        slugs = [r.slug for r in candidates]
        ck2 = make_cache_key("make-decision", {"text_hash": text_hash, "slugs": slugs})
        cached2 = None if bust_cache else await self._cache.get(ck2)
        if cached2:
            result.cache_hits += 1
            decisions = cached2
        else:
            resp2 = await self._provider.complete(
                messages=[Message(role="user", content=_DECISION_PROMPT.format(
                    pages=pages_str,
                    summary=text[:1500],
                    entities=entities,
                ))],
                temperature=0.0,
            )
            result.tokens_used += resp2.total_tokens
            decisions = _parse_json_response(resp2.text)
            await self._cache.set(ck2, decisions)

        # Pass 4: writes based on action
        action = decisions.get("action", "create")
        target = decisions.get("target", "")
        new_slug = decisions.get("new_slug") or ""
        update_content = decisions.get("update_content", "")
        title = p.stem.replace("-", " ").replace("_", " ").title()

        if action == "flag" and target and self._store.page_exists(target):
            with self._store.page_lock(target):
                page = self._store.read_page(target)
                if page:
                    page.status = "contradicted"
                    self._store.write_page(target, page)
            result.pages_flagged.append(target)

        elif action == "update" and target and self._store.page_exists(target):
            with self._store.page_lock(target):
                page = self._store.read_page(target)
                if page:
                    section = update_content or f"## From {p.name}\n\n{text[:1000]}"
                    page.content = page.content.rstrip() + f"\n\n{section}"
                    self._store.write_page(target, page)
            result.pages_updated.append(target)

        else:  # "create" or fallback
            # Don't create a page if there's no content to put in it
            if not text or not text.strip():
                logger.warning("Skipping page creation for %s — no text extracted", source)
                result.skip_reason = "no extractable text"
                result.skipped = True
            else:
                # Reject slugs that look like wiki syntax artifacts rather than real topics
                _SLUG_BLACKLIST = {"wikilinks", "wikilink", "wiki", "obsidian", "dataview"}
                raw_slug = _slugify(new_slug or title)
                slug = raw_slug if raw_slug not in _SLUG_BLACKLIST else _slugify(title)

                if self._store.page_exists(slug):
                    # Slug already exists — never overwrite; append as update instead
                    with self._store.page_lock(slug):
                        page = self._store.read_page(slug)
                        if page:
                            section = f"## From {p.name}\n\n{text[:1500]}"
                            page.content = page.content.rstrip() + f"\n\n{section}"
                            self._store.write_page(slug, page)
                    result.pages_updated.append(slug)
                else:
                    new_page = WikiPage(
                        title=title, tags=tags,
                        content=f"# {title}\n\n{text[:4000]}",
                        status="active", confidence="medium", sources=[],
                        created=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    )
                    with self._store.page_lock(slug):
                        self._store.write_page(slug, new_page)
                    result.pages_created.append(slug)
                    # New pages are orphans until manually linked — no auto-append to index.md.
                    # The dashboard.md "Orphan pages" Dataview table surfaces them for review.

        self._log.log_ingest(source=p.name,
                             pages_created=result.pages_created,
                             pages_updated=result.pages_updated,
                             pages_flagged=result.pages_flagged,
                             tokens=result.tokens_used,
                             cost_usd=result.cost_usd,
                             cache_hits=result.cache_hits)
        await self._audit.record_ingest(src_hash, src_size, source,
                                        (result.pages_created + result.pages_updated
                                         + result.pages_flagged or [title])[0],
                                        result.tokens_used, result.cost_usd)
        return result
