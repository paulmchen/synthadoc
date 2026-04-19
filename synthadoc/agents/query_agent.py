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

        # Knowledge gap detection (disabled when gap_score_threshold <= 0)
        _max_score = max((r.score for r in candidates), default=0.0)
        _gap = self._gap_score_threshold > 0 and (
            len(candidates) < 3 or _max_score < self._gap_score_threshold
        )
        if _gap:
            logger.info(
                "knowledge gap detected — max_score=%.2f, pages=%d, threshold=%.2f",
                _max_score, len(candidates), self._gap_score_threshold,
            )
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
