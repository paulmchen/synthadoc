# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import os
import pytest
from pathlib import Path
from unittest.mock import patch
import click


def _imp():
    from synthadoc.cli._wiki import resolve_wiki, ENV_VAR, DEFAULT_WIKI_FILE, \
        _read_default_wiki, _write_default_wiki
    return resolve_wiki, ENV_VAR, DEFAULT_WIKI_FILE, _read_default_wiki, _write_default_wiki


# --- resolution priority ---

def test_explicit_wins_over_env(monkeypatch):
    resolve_wiki, ENV_VAR, _, _r, _ = _imp()
    monkeypatch.setenv(ENV_VAR, "env-wiki")
    with patch("synthadoc.cli._wiki._read_default_wiki", return_value=None):
        result = resolve_wiki("explicit-wiki")
    assert result == "explicit-wiki"


def test_explicit_wins_over_saved(monkeypatch):
    resolve_wiki, ENV_VAR, _, _r, _ = _imp()
    monkeypatch.delenv(ENV_VAR, raising=False)
    with patch("synthadoc.cli._wiki._read_default_wiki", return_value="saved-wiki"):
        result = resolve_wiki("explicit-wiki")
    assert result == "explicit-wiki"


def test_env_var_used_when_no_explicit(monkeypatch):
    resolve_wiki, ENV_VAR, _, _r, _ = _imp()
    monkeypatch.setenv(ENV_VAR, "env-wiki")
    with patch("synthadoc.cli._wiki._read_default_wiki", return_value=None):
        result = resolve_wiki(None)
    assert result == "env-wiki"


def test_saved_default_used_when_no_explicit_no_env(monkeypatch):
    resolve_wiki, ENV_VAR, _, _r, _ = _imp()
    monkeypatch.delenv(ENV_VAR, raising=False)
    with patch("synthadoc.cli._wiki._read_default_wiki", return_value="saved-wiki"):
        result = resolve_wiki(None)
    assert result == "saved-wiki"


def test_cwd_fallback_when_config_present(monkeypatch, tmp_path):
    resolve_wiki, ENV_VAR, _, _r, _ = _imp()
    monkeypatch.delenv(ENV_VAR, raising=False)
    (tmp_path / ".synthadoc").mkdir()
    (tmp_path / ".synthadoc" / "config.toml").write_text("")
    monkeypatch.chdir(tmp_path)
    with patch("synthadoc.cli._wiki._read_default_wiki", return_value=None):
        result = resolve_wiki(None)
    assert result == "."


def test_error_when_nothing_resolves(monkeypatch, tmp_path):
    resolve_wiki, ENV_VAR, _, _r, _ = _imp()
    monkeypatch.delenv(ENV_VAR, raising=False)
    monkeypatch.chdir(tmp_path)   # no .synthadoc/config.toml here
    with patch("synthadoc.cli._wiki._read_default_wiki", return_value=None):
        with pytest.raises(click.exceptions.Exit) as exc:
            resolve_wiki(None)
    assert exc.value.exit_code == 1


def test_whitespace_env_var_is_ignored(monkeypatch):
    resolve_wiki, ENV_VAR, _, _r, _ = _imp()
    monkeypatch.setenv(ENV_VAR, "   ")
    with patch("synthadoc.cli._wiki._read_default_wiki", return_value="saved"):
        result = resolve_wiki(None)
    assert result == "saved"


# --- _read_default_wiki / _write_default_wiki ---

def test_read_write_roundtrip(tmp_path):
    _, _, _, _read, _write = _imp()
    with patch("synthadoc.cli._wiki.DEFAULT_WIKI_FILE", tmp_path / "default_wiki"):
        assert _read() is None
        _write("my-wiki")
        assert _read() == "my-wiki"
        _write(None)
        assert _read() is None


def test_write_strips_whitespace(tmp_path):
    _, _, _, _read, _write = _imp()
    with patch("synthadoc.cli._wiki.DEFAULT_WIKI_FILE", tmp_path / "default_wiki"):
        _write("  my-wiki  ")
        assert _read() == "my-wiki"


# --- synthadoc use command ---
from typer.testing import CliRunner
from synthadoc.cli.main import app

runner = CliRunner()


def test_use_saves_default(tmp_path):
    """'synthadoc use my-wiki' writes the wiki name as saved default."""
    with patch("synthadoc.cli.main._write_default_wiki") as mock_write, \
         patch("synthadoc.cli.main._resolve_wiki_path",
               return_value=tmp_path) as _:
        (tmp_path / ".synthadoc").mkdir()
        (tmp_path / ".synthadoc" / "config.toml").write_text("")
        result = runner.invoke(app, ["use", "my-wiki"])
    assert result.exit_code == 0
    assert "my-wiki" in result.output
    mock_write.assert_called_once_with("my-wiki")


def test_use_no_arg_shows_env_source(monkeypatch):
    """'synthadoc use' shows active wiki and source when env var is set."""
    from synthadoc.cli._wiki import ENV_VAR
    monkeypatch.setenv(ENV_VAR, "env-wiki")
    result = runner.invoke(app, ["use"])
    assert result.exit_code == 0
    assert "env-wiki" in result.output
    assert ENV_VAR in result.output


def test_use_no_arg_shows_saved_source(monkeypatch):
    """'synthadoc use' shows saved default when env var is absent."""
    from synthadoc.cli._wiki import ENV_VAR
    monkeypatch.delenv(ENV_VAR, raising=False)
    with patch("synthadoc.cli.main._read_default_wiki", return_value="saved-wiki"):
        result = runner.invoke(app, ["use"])
    assert result.exit_code == 0
    assert "saved-wiki" in result.output
    assert "saved default" in result.output


def test_use_no_arg_shows_no_default_message(monkeypatch):
    """'synthadoc use' gives actionable message when nothing is set."""
    from synthadoc.cli._wiki import ENV_VAR
    monkeypatch.delenv(ENV_VAR, raising=False)
    with patch("synthadoc.cli.main._read_default_wiki", return_value=None):
        result = runner.invoke(app, ["use"])
    assert result.exit_code == 0
    assert "synthadoc use <name>" in result.output


def test_use_clear_removes_default():
    """'synthadoc use --clear' calls _write_default_wiki(None)."""
    with patch("synthadoc.cli.main._write_default_wiki") as mock_write:
        result = runner.invoke(app, ["use", "--clear"])
    assert result.exit_code == 0
    mock_write.assert_called_once_with(None)


def test_use_warns_on_unknown_wiki(tmp_path):
    """'synthadoc use unknown' warns but still saves (user may not have server running)."""
    with patch("synthadoc.cli.main._write_default_wiki"), \
         patch("synthadoc.cli.main._resolve_wiki_path", return_value=tmp_path):
        # tmp_path has no .synthadoc/config.toml → unknown wiki
        result = runner.invoke(app, ["use", "unknown-wiki"])
    assert result.exit_code == 0
    assert "Warning" in result.stderr or "not a registered" in result.stderr


# --- per-command integration: env var picked up, stdout stays clean ---
# Note: CliRunner() without mix_stderr=False (not supported in this typer version)
# mixes stderr into result.output. Tests verify correct behaviour via exit_code,
# mock call-site, and presence/absence of expected command output values.

automation_runner = CliRunner()


def test_ingest_uses_env_var(monkeypatch):
    """When SYNTHADOC_WIKI is set, ingest picks it up and succeeds."""
    from synthadoc.cli._wiki import ENV_VAR
    monkeypatch.setenv(ENV_VAR, "my-wiki")
    with patch("synthadoc.cli.ingest.post", return_value={"job_id": "j1"}) as mock_post:
        result = automation_runner.invoke(app, ["ingest", "https://example.com/doc"])
    assert result.exit_code == 0
    assert "j1" in result.output              # job id in output
    # Verify the correct wiki was passed to the HTTP helper
    assert mock_post.call_args[0][0] == "my-wiki"


def test_query_uses_env_var(monkeypatch):
    """When SYNTHADOC_WIKI is set, query picks it up and shows answer."""
    from synthadoc.cli._wiki import ENV_VAR
    monkeypatch.setenv(ENV_VAR, "my-wiki")
    with patch("synthadoc.cli.query.get", return_value={
        "answer": "Test answer", "citations": [], "knowledge_gap": False, "suggested_searches": []
    }) as mock_get:
        result = automation_runner.invoke(app, ["query", "what is turing?"])
    assert result.exit_code == 0
    assert "Test answer" in result.output
    assert mock_get.call_args[0][0] == "my-wiki"


def test_jobs_list_uses_env_var(monkeypatch):
    """When SYNTHADOC_WIKI is set, jobs list picks it up and succeeds."""
    from synthadoc.cli._wiki import ENV_VAR
    monkeypatch.setenv(ENV_VAR, "my-wiki")
    with patch("synthadoc.cli.jobs.get", return_value=[]) as mock_get:
        result = automation_runner.invoke(app, ["jobs", "list"])
    assert result.exit_code == 0
    assert mock_get.call_args[0][0] == "my-wiki"


def test_status_uses_saved_default(monkeypatch):
    """When saved default is set and no env var, status uses the saved default."""
    from synthadoc.cli._wiki import ENV_VAR
    monkeypatch.delenv(ENV_VAR, raising=False)
    with patch("synthadoc.cli._wiki._read_default_wiki", return_value="saved-wiki"), \
         patch("synthadoc.cli.status.get", return_value={
             "wiki": "/fake", "pages": 5, "jobs_pending": 0, "jobs_total": 0
         }) as mock_get:
        result = automation_runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert mock_get.call_args[0][0] == "saved-wiki"


def test_lint_report_uses_env_var(monkeypatch, tmp_path):
    """When SYNTHADOC_WIKI is set, lint report picks it up and succeeds."""
    from synthadoc.cli._wiki import ENV_VAR
    monkeypatch.setenv(ENV_VAR, "my-wiki")
    fake_wiki_dir = tmp_path / "wiki"
    fake_wiki_dir.mkdir()
    with patch("synthadoc.cli.install.resolve_wiki_path", return_value=tmp_path) as mock_rwp, \
         patch("synthadoc.cli.lint.find_orphan_slugs", return_value=[]), \
         patch("synthadoc.cli.lint._sync_orphan_frontmatter"):
        result = automation_runner.invoke(app, ["lint", "report"])
    assert result.exit_code == 0
    assert mock_rwp.call_args[0][0] == "my-wiki"


def test_explicit_w_overrides_env_and_hint_on_stderr(monkeypatch):
    """Explicit -w overrides SYNTHADOC_WIKI and the override hint appears in output."""
    from synthadoc.cli._wiki import ENV_VAR
    monkeypatch.setenv(ENV_VAR, "env-wiki")
    with patch("synthadoc.cli.status.get", return_value={
        "wiki": "/fake", "pages": 5, "jobs_pending": 0, "jobs_total": 0
    }) as mock_get:
        result = automation_runner.invoke(app, ["status", "-w", "explicit-wiki"])
    assert result.exit_code == 0
    # explicit-wiki was used (not env-wiki)
    assert mock_get.call_args[0][0] == "explicit-wiki"
    # override hint is emitted (goes to stderr, mixed into output by CliRunner)
    assert "overrides" in result.output


def test_no_wiki_exits_1_with_helpful_stderr(monkeypatch, tmp_path):
    """When no wiki context exists, command exits 1 with actionable message."""
    from synthadoc.cli._wiki import ENV_VAR
    monkeypatch.delenv(ENV_VAR, raising=False)
    monkeypatch.chdir(tmp_path)
    with patch("synthadoc.cli._wiki._read_default_wiki", return_value=None):
        result = automation_runner.invoke(app, ["status"])
    assert result.exit_code == 1
    # Actionable hint appears (goes to stderr, mixed into output by CliRunner)
    assert "synthadoc use" in result.output


def test_saved_default_hint_on_stderr_not_stdout(monkeypatch):
    """When saved default resolves the wiki, the hint contains the wiki name."""
    from synthadoc.cli._wiki import ENV_VAR
    monkeypatch.delenv(ENV_VAR, raising=False)
    with patch("synthadoc.cli._wiki._read_default_wiki", return_value="saved-wiki"), \
         patch("synthadoc.cli.jobs.get", return_value=[]) as mock_get:
        result = automation_runner.invoke(app, ["jobs", "list"])
    assert result.exit_code == 0
    assert mock_get.call_args[0][0] == "saved-wiki"
    # The hint mentioning saved-wiki appears (goes to stderr, mixed into output)
    assert "saved-wiki" in result.output
