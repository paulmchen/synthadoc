# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
from synthadoc.agents.ingest_agent import _confidence_passes_threshold


def test_high_passes_high_threshold():
    assert _confidence_passes_threshold("high", "high") is True


def test_medium_fails_high_threshold():
    assert _confidence_passes_threshold("medium", "high") is False


def test_low_fails_medium_threshold():
    assert _confidence_passes_threshold("low", "medium") is False


def test_high_passes_low_threshold():
    assert _confidence_passes_threshold("high", "low") is True


def test_medium_passes_low_threshold():
    assert _confidence_passes_threshold("medium", "low") is True


def test_unknown_confidence_fails():
    assert _confidence_passes_threshold("unknown", "high") is False


def test_high_passes_medium_threshold():
    assert _confidence_passes_threshold("high", "medium") is True
