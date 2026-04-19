# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
from synthadoc.providers.pricing import estimate_cost


def test_known_model_uses_separate_input_output_rates():
    """claude-haiku input ($1/M) and output ($5/M) rates applied separately."""
    cost = estimate_cost("claude-haiku-4-5-20251001", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 6.0) < 0.001  # $1 input + $5 output


def test_known_model_gpt4o_mini():
    """gpt-4o-mini: $0.15/M input, $0.60/M output."""
    cost = estimate_cost("gpt-4o-mini", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 0.75) < 0.001  # $0.15 + $0.60


def test_ollama_is_always_zero():
    """Local inference has no cost regardless of token count."""
    assert estimate_cost("llama3", input_tokens=999_999, output_tokens=999_999, is_local=True) == 0.0


def test_unknown_model_uses_fallback_rate():
    """Unknown models use a conservative fallback rather than crashing."""
    cost = estimate_cost("some-future-model", input_tokens=1_000_000, output_tokens=0)
    assert cost > 0.0


def test_zero_tokens_returns_zero():
    cost = estimate_cost("gpt-4o", input_tokens=0, output_tokens=0)
    assert cost == 0.0


def test_gemini_flash_rates():
    """gemini-2.0-flash: $0.30/M input, $2.50/M output."""
    cost = estimate_cost("gemini-2.0-flash", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(cost - 2.80) < 0.001  # $0.30 + $2.50
