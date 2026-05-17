# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from pathlib import Path
from unittest.mock import patch
from typer.testing import CliRunner
from synthadoc.cli.main import app

runner = CliRunner()


def test_context_build_calls_api(tmp_path):
    with patch("synthadoc.cli.context._build_context_pack") as mock_build:
        mock_build.return_value = "# Context Pack\nContent."
        result = runner.invoke(app, ["context", "build", "early computing",
                                     "--wiki-root", str(tmp_path)])
        assert result.exit_code == 0, result.output
        mock_build.assert_called_once()


def test_context_build_output_to_file(tmp_path):
    out = tmp_path / "context.md"
    with patch("synthadoc.cli.context._build_context_pack") as mock_build:
        mock_build.return_value = "# Context Pack\nContent."
        result = runner.invoke(app, ["context", "build", "early computing",
                                     "--output", str(out),
                                     "--wiki-root", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert out.exists()
        assert "Context Pack" in out.read_text()


def test_context_build_with_wiki_flag(tmp_path):
    """context build --wiki (no --wiki-root) resolves wiki by name."""
    with patch("synthadoc.cli.context._build_context_pack") as mock_build:
        mock_build.return_value = "# Pack\n"
        result = runner.invoke(app, [
            "context", "build", "topic", "--wiki", str(tmp_path),
        ])
    assert result.exit_code == 0, result.output
    mock_build.assert_called_once_with(str(tmp_path), "topic", 4000)


def test_build_context_pack_constructs_pages(tmp_path):
    """_build_context_pack assembles ContextPack from server response and returns Markdown."""
    from synthadoc.cli.context import _build_context_pack
    mock_response = {
        "goal": "early computing",
        "token_budget": 4000,
        "tokens_used": 150,
        "pages": [{
            "slug": "eniac", "relevance": 0.9, "excerpt": "first computer",
            "source": "source.md", "confidence": "high", "tags": [],
            "estimated_tokens": 100,
        }],
        "omitted": [{"slug": "babbage", "estimated_tokens": 200}],
    }
    with patch("synthadoc.cli._http.post", return_value=mock_response):
        result = _build_context_pack(str(tmp_path), "early computing", 4000)
    assert "early computing" in result
    assert "eniac" in result
