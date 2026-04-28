# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
from synthadoc.agents._utils import parse_json_string_array


# ── happy path ────────────────────────────────────────────────────────────────

def test_basic_array():
    assert parse_json_string_array('["a", "b", "c"]', 4) == ["a", "b", "c"]


def test_strips_json_fenced_block():
    text = '```json\n["zone map", "frost dates"]\n```'
    assert parse_json_string_array(text, 4) == ["zone map", "frost dates"]


def test_strips_plain_fenced_block():
    text = '```\n["zone map", "frost dates"]\n```'
    assert parse_json_string_array(text, 4) == ["zone map", "frost dates"]


def test_respects_max_items():
    assert parse_json_string_array('["a", "b", "c", "d", "e"]', 3) == ["a", "b", "c"]


def test_single_element_array():
    assert parse_json_string_array('["only one"]', 4) == ["only one"]


def test_filters_whitespace_only_strings():
    result = parse_json_string_array('["valid", "   ", "\\t", "also valid"]', 4)
    assert result == ["valid", "also valid"]


def test_coerces_non_string_elements():
    assert parse_json_string_array('[1, 2, 3]', 4) == ["1", "2", "3"]


def test_leading_trailing_whitespace_around_json():
    assert parse_json_string_array('  \n["a", "b"]\n  ', 4) == ["a", "b"]


# ── fallback → None ───────────────────────────────────────────────────────────

def test_empty_text_returns_none():
    assert parse_json_string_array("", 4) is None


def test_prose_text_returns_none():
    assert parse_json_string_array("This is not JSON.", 4) is None


def test_empty_array_returns_none():
    assert parse_json_string_array("[]", 4) is None


def test_json_object_returns_none():
    assert parse_json_string_array('{"queries": ["a"]}', 4) is None


def test_all_whitespace_elements_returns_none():
    assert parse_json_string_array('["  ", "\t", ""]', 4) is None


def test_max_items_zero_returns_none():
    assert parse_json_string_array('["a", "b"]', 0) is None


def test_malformed_json_returns_none():
    assert parse_json_string_array('["a", "b"', 4) is None


def test_only_fence_lines_returns_none():
    assert parse_json_string_array("```\n```", 4) is None
