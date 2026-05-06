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
