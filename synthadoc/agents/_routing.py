# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import json
import re

from synthadoc.providers.base import Message


async def pick_routing_branches(
    provider,
    branches: dict[str, list[str]],
    context: str,
    *,
    multi: bool,
) -> list[str]:
    """Ask the LLM to select branch names from a ROUTING.md index.

    Args:
        provider:  LLM provider instance.
        branches:  Branch mapping from RoutingIndex.branches.
        context:   Free-text description of what needs to be placed/searched
                   (e.g. page title+tags for ingest, question text for query).
        multi:     False → pick exactly one branch (ingest placement).
                   True  → pick 1-2 branches (query scoping); returns [] when
                   no branch is clearly relevant so caller can fall back to
                   full-corpus search.
    """
    if not branches:
        return []

    branch_list = "\n".join(f"- {b}" for b in branches)
    if multi:
        prompt = (
            f"Wiki topic branches:\n{branch_list}\n\n"
            f"{context}\n\n"
            "Return a JSON array of the 1-2 most relevant branch names. "
            "Return [] if no branch is clearly relevant."
        )
    else:
        prompt = (
            f"Wiki topic branches:\n{branch_list}\n\n"
            f"{context}\n\n"
            "Return the single most appropriate branch name for this page. "
            "Return exactly one branch name from the list above."
        )

    try:
        resp = await provider.complete(
            messages=[Message(role="user", content=prompt)],
            temperature=0.0,
        )
    except Exception:
        return []

    if multi:
        m = re.search(r"\[.*?\]", resp.text, re.DOTALL)
        if not m:
            return []
        try:
            result = json.loads(m.group())
            return [b for b in result if b in branches]
        except Exception:
            return []
    else:
        candidate = resp.text.strip().strip('"').strip()
        return [candidate] if candidate in branches else [next(iter(branches))]
