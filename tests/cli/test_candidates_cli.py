# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from pathlib import Path
import tomllib
import pytest
from typer.testing import CliRunner
from synthadoc.cli.main import app

runner = CliRunner()


def _make_wiki_with_candidate(tmp_path: Path) -> Path:
    (tmp_path / "wiki" / "candidates").mkdir(parents=True)
    (tmp_path / "wiki" / "candidates" / "new-page.md").write_text(
        "---\ntitle: New Page\nconfidence: low\ncreated: '2026-05-05'\ntags: []\nstatus: active\nsources: []\n---\n\nContent."
    )
    cfg_dir = tmp_path / ".synthadoc"
    cfg_dir.mkdir()
    (cfg_dir / "config.toml").write_text('[ingest]\nstaging_policy = "threshold"\n')
    return tmp_path


def test_staging_policy_show(tmp_path):
    w = _make_wiki_with_candidate(tmp_path)
    result = runner.invoke(app, ["staging", "policy", "--wiki-root", str(w)])
    assert result.exit_code == 0, result.output
    assert "threshold" in result.output


def test_staging_policy_set_off(tmp_path):
    w = _make_wiki_with_candidate(tmp_path)
    result = runner.invoke(app, ["staging", "policy", "off", "--wiki-root", str(w)])
    assert result.exit_code == 0, result.output
    cfg = tomllib.loads((w / ".synthadoc" / "config.toml").read_text())
    assert cfg["ingest"]["staging_policy"] == "off"


def test_candidates_list(tmp_path):
    w = _make_wiki_with_candidate(tmp_path)
    result = runner.invoke(app, ["candidates", "list", "--wiki-root", str(w)])
    assert result.exit_code == 0, result.output
    assert "new-page" in result.output


def test_candidates_promote(tmp_path):
    w = _make_wiki_with_candidate(tmp_path)
    (w / "wiki").mkdir(exist_ok=True)
    result = runner.invoke(app, ["candidates", "promote", "new-page", "--wiki-root", str(w)])
    assert result.exit_code == 0, result.output
    assert (w / "wiki" / "new-page.md").exists()
    assert not (w / "wiki" / "candidates" / "new-page.md").exists()


def test_candidates_discard(tmp_path):
    w = _make_wiki_with_candidate(tmp_path)
    result = runner.invoke(app, ["candidates", "discard", "new-page", "--wiki-root", str(w)])
    assert result.exit_code == 0, result.output
    assert not (w / "wiki" / "candidates" / "new-page.md").exists()


def test_candidates_list_empty(tmp_path):
    (tmp_path / "wiki" / "candidates").mkdir(parents=True)
    result = runner.invoke(app, ["candidates", "list", "--wiki-root", str(tmp_path)])
    assert result.exit_code == 0
    assert "No candidates" in result.output
