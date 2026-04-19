# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import io
import sys
import pytest
from synthadoc.cli.logo import (
    _c, _color_supported, _GREEN, _RESET, banner_text, print_banner,
)


def test_banner_text_contains_synthadoc():
    text = banner_text()
    assert "SYNTHADOC" in text or "S Y N T H A D O C" in text


def test_banner_text_contains_version():
    from synthadoc import __version__
    text = banner_text(version=__version__)
    assert __version__ in text


def test_banner_text_is_plain_ascii():
    text = banner_text()
    assert "\033[" not in text


def test_c_applies_code_when_color_enabled():
    result = _c(_GREEN, "hello", True)
    assert result == f"{_GREEN}hello{_RESET}"


def test_c_returns_plain_text_when_color_disabled():
    result = _c(_GREEN, "hello", False)
    assert result == "hello"


def test_color_not_supported_with_no_color_env(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    assert _color_supported() is False


def test_color_not_supported_with_dumb_term(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "dumb")
    assert _color_supported() is False


def test_print_banner_outputs_port_and_wiki(monkeypatch, capsys):
    monkeypatch.setenv("NO_COLOR", "1")
    print_banner(port=8080, wiki="test-wiki", version="0.1.0")
    captured = capsys.readouterr().out
    assert "8080" in captured
    assert "test-wiki" in captured


def test_print_banner_includes_mode(monkeypatch, capsys):
    monkeypatch.setenv("NO_COLOR", "1")
    print_banner(port=7070, wiki="w", mode="HTTP only")
    captured = capsys.readouterr().out
    assert "HTTP only" in captured
