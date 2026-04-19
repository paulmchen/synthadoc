# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""Per-model LLM pricing table.

Refresh at each major release. Update _LAST_UPDATED and the rates below.
Sources (checked 2026-04-18):
  Anthropic — https://docs.anthropic.com/en/docs/about-claude/pricing
  OpenAI    — https://openai.com/api/pricing/
  Gemini    — https://ai.google.dev/gemini-api/docs/pricing
  Groq      — https://groq.com/pricing
"""
from __future__ import annotations

_LAST_UPDATED = "2026-04-18"

# (input_usd_per_token, output_usd_per_token)
_PRICING: dict[str, tuple[float, float]] = {
    # Anthropic
    "claude-opus-4-7":                       (5.00e-6, 25.00e-6),
    "claude-sonnet-4-6":                     (3.00e-6, 15.00e-6),
    "claude-haiku-4-5-20251001":             (1.00e-6,  5.00e-6),
    # OpenAI
    "gpt-4o":                                (2.50e-6, 10.00e-6),
    "gpt-4o-mini":                           (0.15e-6,  0.60e-6),
    # Gemini (via OpenAI-compatible endpoint)
    "gemini-2.0-flash":                      (0.30e-6,  2.50e-6),
    "gemini-1.5-pro":                        (2.50e-6, 10.00e-6),
    # Groq
    "llama-3.3-70b-versatile":               (0.59e-6,  0.79e-6),
    "llama4-scout-17b-16e-instruct":         (0.11e-6,  0.34e-6),
    "llama4-maverick-17b-128e-instruct":     (0.50e-6,  0.77e-6),
}

# Conservative fallback for models not in the table — avoids silent $0 underreporting
_FALLBACK: tuple[float, float] = (3.00e-6, 3.00e-6)


def estimate_cost(model: str, input_tokens: int, output_tokens: int,
                  is_local: bool = False) -> float:
    """Return estimated cost in USD for a single LLM call.

    Pass is_local=True for Ollama (always $0.00).
    Unknown models use a conservative fallback rate.
    """
    if is_local:
        return 0.0
    rates = _PRICING.get(model, _FALLBACK)
    return input_tokens * rates[0] + output_tokens * rates[1]
