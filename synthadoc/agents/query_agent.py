# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field

from synthadoc.agents.search_decompose_agent import SearchDecomposeAgent
from synthadoc.providers.base import LLMProvider, Message
from synthadoc.storage.search import HybridSearch
from synthadoc.storage.wiki import WikiStorage

logger = logging.getLogger(__name__)

_MAX_SUB_QUESTIONS = 4
_MAX_QUESTION_CHARS = 4000

# Stopwords excluded when extracting key terms for the content-overlap gap check.
# Keep this list lean — a false positive (treating a content word as a stopword)
# suppresses gap detection; a false negative (missing a stopword) is harmless.
_STOPWORDS = frozenset({
    "what", "when", "where", "which", "who", "whom", "whose", "why", "how",
    "should", "would", "could", "will", "does", "have", "with", "that", "this",
    "they", "them", "their", "there", "then", "than", "also", "well", "just",
    "some", "more", "very", "much", "many", "most", "from", "into", "onto",
    "about", "after", "before", "between", "during", "through",
    "these", "those", "each", "both", "your", "mine", "ours",
    "start", "grow", "good", "best", "make", "need", "want",
})


@dataclass
class QueryResult:
    question: str
    answer: str
    citations: list[str]
    tokens_used: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    knowledge_gap: bool = False
    suggested_searches: list[str] = field(default_factory=list)


class QueryAgent:
    def __init__(self, provider: LLMProvider, store: WikiStorage,
                 search: HybridSearch, top_n: int = 8,
                 gap_score_threshold: float = 2.0) -> None:
        self._provider = provider
        self._store = store
        self._search = search
        self._top_n = top_n
        self._gap_score_threshold = gap_score_threshold

    async def decompose(self, question: str) -> list[str]:
        """Break a question into focused sub-questions for independent retrieval.

        Returns [question] on any failure so callers always get a usable list.
        """
        truncated = question[:_MAX_QUESTION_CHARS]
        try:
            resp = await self._provider.complete(
                messages=[Message(role="user",
                    content=(
                        f"Break this question into focused sub-questions for a knowledge base lookup.\n"
                        f"Simple questions should return a single-element list.\n"
                        f"Return a JSON array of strings only. No explanation.\n\n"
                        f"Question: {truncated}"
                    ))],
                temperature=0.0,
            )
            text = resp.text.strip()
            if text.startswith("```"):
                # Strip markdown code fences that some models add despite instructions
                lines = text.splitlines()
                text = "\n".join(
                    l for l in lines
                    if not l.strip().startswith("```")
                ).strip()
            parts = json.loads(text)
            if isinstance(parts, list) and parts:
                filtered = [str(q) for q in parts[:_MAX_SUB_QUESTIONS] if str(q).strip()]
                if filtered:
                    if len(filtered) == 1:
                        logger.info("query is simple — no decomposition (1 sub-question)")
                    else:
                        logger.info(
                            "query decomposed into %d sub-question(s): %s",
                            len(filtered),
                            " | ".join(f'"{q}"' for q in filtered),
                        )
                    return filtered
        except Exception as exc:
            logger.warning(
                "decompose failed (%s: %s) — falling back to original question",
                type(exc).__name__, exc,
            )
        return [question]

    async def query(self, question: str) -> QueryResult:
        sub_questions = await self.decompose(question)

        async def _search_one(sub_q: str):
            return self._search.bm25_search(sub_q.lower().split(), top_n=self._top_n)

        results_per_sub = await asyncio.gather(*[_search_one(q) for q in sub_questions])

        best: dict[str, object] = {}
        for results in results_per_sub:
            for r in results:
                if r.slug not in best or r.score > best[r.slug].score:
                    best[r.slug] = r
        candidates = sorted(best.values(), key=lambda r: r.score, reverse=True)[:self._top_n]

        # ── Knowledge gap detection ────────────────────────────────────────────
        # Three independent signals; any one triggers the gap:
        #
        #   1. Page count < 3  — wiki has almost nothing on the topic.
        #
        #   2. Max BM25 score < gap_score_threshold  — pages exist but their
        #      keyword overlap with the query is weak (tunable via
        #      [query] gap_score_threshold in synthadoc.toml; default 2.0).
        #
        #   3. Content overlap < 2  — BM25 scores are corpus-relative and can
        #      be inflated by shared vocabulary even when pages are off-topic
        #      (e.g. spring-flower pages match a vegetables query because both
        #      use words like "spring", "planting", "Canada").  This check
        #      counts how many retrieved pages actually contain at least one
        #      key noun from the question.  Key terms = question words longer
        #      than 4 chars that are not in _STOPWORDS, stem-truncated by 2
        #      chars for basic suffix matching (vegetable → vegetabl).
        #      If fewer than 2 pages pass this test, the wiki lacks on-topic
        #      content regardless of BM25 scores.
        #
        # Set gap_score_threshold = 0 to disable gap detection entirely.
        _max_score = max((r.score for r in candidates), default=0.0)

        # Extract meaningful content words from the question for the overlap check.
        # Strip 1 char for basic plural/suffix matching ("vegetables" → "vegetable",
        # "indoors" → "indoor"). Stripping 2 chars was too aggressive — it turned
        # "Canadian" into "canadi", which still matched every page in a Canada-focused
        # wiki and made the check useless as a discriminator.
        _key_terms = {
            w.lower().rstrip("s?!.,")        # strip plural/punctuation only
            for w in question.split()
            if len(w) > 4 and w.lower().rstrip("s?!.,") not in _STOPWORDS
        }

        # Signal 3: check whether retrieved pages contain dedicated coverage of the
        # query's specific topic words.
        #
        # Generic corpus terms ("canadian", "spring", "plant") appear in nearly
        # every page and would make every page look on-topic.  We filter them out
        # by excluding terms whose document frequency exceeds 60% of the candidates.
        # From the remaining "specific" terms we check whether at least 2 candidates
        # contain ANY of them with meaningful frequency (≥ 2 occurrences).
        #
        # Using ANY rather than a single rarest term handles multi-aspect queries
        # correctly: a page about "full shade" plants is on-topic for a query about
        # "sun, partial shade, and full shade" even if it lacks the word "partial".
        #
        # Zero-freq terms (synonyms like "backyard" vs "garden") are excluded;
        # they reflect vocabulary mismatch, not missing content.
        _MIN_TERM_FREQ = 2
        if _key_terms and candidates:
            # Count how many candidates contain each key term (doc frequency).
            _term_doc_freq = {
                t: sum(
                    1 for r in candidates
                    if (p := self._store.read_page(r.slug)) and t in p.content.lower()
                )
                for t in _key_terms
            }
            _covered = {t: f for t, f in _term_doc_freq.items() if f > 0}

            # Drop hyper-generic terms that appear in >80% of candidates.
            # Using 80% (not 60%) so moderately-common topic words like "partial"
            # (present in ~60-70% of pages in a shade-focused wiki) are kept as
            # discriminators rather than being wrongly discarded as generic.
            _n_cands = len(candidates)
            _specific = {t: f for t, f in _covered.items() if f <= _n_cands * 0.8}
            if not _specific:
                _specific = _covered  # all terms are corpus-generic; use full covered set
            # If every term in _specific appears in only one page it is too rare to
            # discriminate topic coverage — expand to include all covered terms.
            elif max(_specific.values()) <= 1:
                _specific = _covered

            # Log the rarest specific term as a representative discriminator.
            if _specific:
                _discriminating_term = min(_specific, key=lambda t: _specific[t])
            elif _covered:
                _discriminating_term = min(_covered, key=lambda t: _covered[t])
            else:
                _discriminating_term = min(_term_doc_freq, key=lambda t: _term_doc_freq[t])

            # A page is on-topic if it mentions ANY specific term with sufficient freq.
            _pages_with_overlap = sum(
                1 for r in candidates
                if (p := self._store.read_page(r.slug)) and
                   any(p.content.lower().count(t) >= _MIN_TERM_FREQ for t in _specific)
            )
        else:
            _discriminating_term = ""
            _pages_with_overlap = len(candidates)   # no key terms → skip check

        _gap = self._gap_score_threshold > 0 and (
            len(candidates) < 3                          # signal 1: too few pages
            or _max_score < self._gap_score_threshold    # signal 2: low BM25 scores
            or _pages_with_overlap < 2                   # signal 3: no dedicated coverage
        )

        # Always log retrieval quality so operators can tune gap_score_threshold.
        logger.info(
            "query retrieval — pages=%d, max_score=%.2f, "
            "discriminating_term=%r, on_topic_pages=%d, gap=%s",
            len(candidates), _max_score, _discriminating_term, _pages_with_overlap, _gap,
        )
        if _gap:
            _suggested = await SearchDecomposeAgent(self._provider).decompose(question)
        else:
            _suggested = []

        citations = [r.slug for r in candidates]
        context = "\n\n".join(
            f"### {p.title}\n{p.content[:1000]}"
            for r in candidates
            if (p := self._store.read_page(r.slug))
        ) or "No relevant pages found."

        resp2 = await self._provider.complete(
            messages=[Message(role="user",
                content=f"Answer using ONLY these wiki pages. Cite with [[PageTitle]].\n\n"
                        f"Question: {question}\n\nPages:\n{context}")],
            temperature=0.0,
        )
        logger.info("query answered — %d page(s) cited, %d tokens",
                    len(citations), resp2.total_tokens)
        return QueryResult(
            question=question,
            answer=resp2.text,
            citations=citations,
            tokens_used=resp2.total_tokens,
            input_tokens=resp2.input_tokens,
            output_tokens=resp2.output_tokens,
            knowledge_gap=_gap,
            suggested_searches=_suggested,
        )
