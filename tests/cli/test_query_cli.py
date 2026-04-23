# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
from typer.testing import CliRunner
from unittest.mock import patch
from synthadoc.cli.main import app

runner = CliRunner()


def _mock_get(response: dict):
    """Patch synthadoc.cli._http.get to return response."""
    return patch("synthadoc.cli.query.get", return_value=response)


def _capture_get(response: dict):
    """Patch get and capture the kwargs it was called with."""
    from unittest.mock import MagicMock
    mock = MagicMock(return_value=response)
    return patch("synthadoc.cli.query.get", mock), mock


def test_query_cli_no_gap_shows_only_answer():
    """When knowledge_gap=False, no callout must appear in output."""
    with _mock_get({"answer": "AI is great.", "citations": ["ai-page"],
                    "knowledge_gap": False, "suggested_searches": []}):
        result = runner.invoke(app, ["query", "What is AI?", "-w", "."])
    assert "AI is great." in result.output
    assert "Knowledge Gap" not in result.output


def test_query_cli_gap_shows_callout():
    """When knowledge_gap=True, the [!tip] callout must appear."""
    with _mock_get({
        "answer": "No info found.",
        "citations": [],
        "knowledge_gap": True,
        "suggested_searches": ["canadian spring vegetables", "frost dates Canada"],
    }):
        result = runner.invoke(app, ["query", "Vegetables in Canada?", "-w", "my-wiki"])
    assert "[!tip] Knowledge Gap Detected" in result.output
    assert "canadian spring vegetables" in result.output
    assert "frost dates Canada" in result.output


def test_query_cli_gap_includes_wiki_name_in_terminal_commands():
    """Terminal ingest commands must include -w <wiki> from the CLI flag."""
    with _mock_get({
        "answer": "No info.",
        "citations": [],
        "knowledge_gap": True,
        "suggested_searches": ["vegetable planting guide"],
    }):
        result = runner.invoke(app, ["query", "Vegetables?", "-w", "yard-gardening-in-canada"])
    assert '-w yard-gardening-in-canada' in result.output


def test_query_cli_gap_includes_command_palette_hint():
    """Callout must mention Obsidian Command Palette when gap detected."""
    with _mock_get({
        "answer": "No info.",
        "citations": [],
        "knowledge_gap": True,
        "suggested_searches": ["test query"],
    }):
        result = runner.invoke(app, ["query", "Something?", "-w", "my-wiki"])
    assert "Command Palette" in result.output
    assert "Synthadoc: Ingest: web search" in result.output


def test_query_cli_default_timeout_is_60():
    """Without --timeout, get() must be called with timeout=60."""
    ctx, mock = _capture_get({"answer": "ok", "citations": [], "knowledge_gap": False})
    with ctx:
        runner.invoke(app, ["query", "What is AI?", "-w", "."])
    _, kwargs = mock.call_args
    assert kwargs.get("timeout") == 60


def test_query_cli_custom_timeout_forwarded():
    """--timeout N must be forwarded to get() as timeout=N."""
    ctx, mock = _capture_get({"answer": "ok", "citations": [], "knowledge_gap": False})
    with ctx:
        runner.invoke(app, ["query", "What is AI?", "-w", ".", "--timeout", "120"])
    _, kwargs = mock.call_args
    assert kwargs.get("timeout") == 120


def test_query_cli_gap_includes_requery_hint():
    """Callout must tell user to re-run their query after ingesting."""
    with _mock_get({
        "answer": "No info.",
        "citations": [],
        "knowledge_gap": True,
        "suggested_searches": ["test"],
    }):
        result = runner.invoke(app, ["query", "Something?", "-w", "my-wiki"])
    assert "re-run" in result.output.lower() or "re-run" in result.output
