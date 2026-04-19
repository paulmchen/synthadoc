# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import json
import logging

from synthadoc.providers.base import LLMProvider, Message

logger = logging.getLogger(__name__)

_MAX_SUB_QUERIES = 4
_MAX_QUERY_CHARS = 2000


class SearchDecomposeAgent:
    """Decomposes a web search intent into focused keyword search strings.

    Unlike QueryAgent.decompose() which produces natural-language sub-questions,
    this agent produces terse keyword strings optimised for web search engines.
    """

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    async def decompose(self, query: str) -> list[str]:
        """Break a search query into focused keyword search strings.

        Returns [query] on any failure so callers always get a usable list.
        """
        truncated = query[:_MAX_QUERY_CHARS]
        try:
            resp = await self._provider.complete(
                messages=[Message(role="user", content=(
                    "You are a search query optimiser. "
                    "Break the topic below into focused keyword search queries "
                    "suitable for a web search engine. "
                    "Each query should be terse (3-7 words), target a different aspect, "
                    "and together provide comprehensive coverage of the topic. "
                    "Simple topics should return a single-element list. "
                    "Return a JSON array of strings only. No explanation.\n\n"
                    f"Topic: {truncated}"
                ))],
                temperature=0.0,
            )
            text = resp.text.strip()
            if text.startswith("```"):
                lines = text.splitlines()
                text = "\n".join(
                    l for l in lines if not l.strip().startswith("```")
                ).strip()
            parts = json.loads(text)
            if isinstance(parts, list) and parts:
                filtered = [str(q) for q in parts[:_MAX_SUB_QUERIES] if str(q).strip()]
                if filtered:
                    if len(filtered) == 1:
                        logger.info("web search is simple — no decomposition (1 query)")
                    else:
                        logger.info(
                            "web search decomposed into %d queries: %s",
                            len(filtered),
                            " | ".join(f'"{q}"' for q in filtered),
                        )
                    return filtered
        except Exception as exc:
            logger.warning(
                "search decompose failed (%s: %s) — falling back to original query",
                type(exc).__name__, exc,
            )
        return [query]
