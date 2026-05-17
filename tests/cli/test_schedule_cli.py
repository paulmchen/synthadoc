# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from pathlib import Path
from unittest.mock import MagicMock, patch
from typer.testing import CliRunner
from synthadoc.cli.main import app

runner = CliRunner()


def _make_wiki(tmp_path: Path) -> Path:
    (tmp_path / ".synthadoc").mkdir(exist_ok=True)
    (tmp_path / ".synthadoc" / "config.toml").write_text(
        '[wiki]\ndomain = "Test"\n[server]\nport = 7070\n[schedule]\njobs = []\n',
        encoding="utf-8",
    )
    return tmp_path


def test_schedule_add_uninstalled_wiki_exits(tmp_path):
    """schedule add without config.toml exits non-zero."""
    result = runner.invoke(app, [
        "schedule", "add", "--op", "lint", "--cron", "0 * * * *",
        "--wiki", str(tmp_path),
    ])
    assert result.exit_code != 0


def test_schedule_add_calls_scheduler(tmp_path):
    wiki = _make_wiki(tmp_path)
    mock_sched = MagicMock()
    mock_sched.add.return_value = "sched-001"
    with patch("synthadoc.core.scheduler.Scheduler", return_value=mock_sched):
        result = runner.invoke(app, [
            "schedule", "add", "--op", "lint", "--cron", "0 * * * *",
            "--wiki", str(wiki),
        ])
    assert result.exit_code == 0, result.output
    assert "sched-001" in result.output
    mock_sched.add.assert_called_once()


def test_schedule_list_shows_entries(tmp_path):
    wiki = _make_wiki(tmp_path)
    entry = MagicMock()
    entry.id = "sched-001"
    entry.cron = "0 * * * *"
    entry.op = "lint"
    mock_sched = MagicMock()
    mock_sched.list.return_value = [entry]
    with patch("synthadoc.core.scheduler.Scheduler", return_value=mock_sched):
        result = runner.invoke(app, ["schedule", "list", "--wiki", str(wiki)])
    assert result.exit_code == 0, result.output
    assert "sched-001" in result.output
    assert "lint" in result.output


def test_schedule_list_empty(tmp_path):
    wiki = _make_wiki(tmp_path)
    mock_sched = MagicMock()
    mock_sched.list.return_value = []
    with patch("synthadoc.core.scheduler.Scheduler", return_value=mock_sched):
        result = runner.invoke(app, ["schedule", "list", "--wiki", str(wiki)])
    assert result.exit_code == 0, result.output


def test_schedule_remove_calls_scheduler(tmp_path):
    wiki = _make_wiki(tmp_path)
    mock_sched = MagicMock()
    with patch("synthadoc.core.scheduler.Scheduler", return_value=mock_sched):
        result = runner.invoke(app, [
            "schedule", "remove", "sched-001", "--wiki", str(wiki),
        ])
    assert result.exit_code == 0, result.output
    assert "sched-001" in result.output
    mock_sched.remove.assert_called_once_with("sched-001")


def test_schedule_apply_registers_jobs(tmp_path):
    wiki = _make_wiki(tmp_path)
    (wiki / ".synthadoc" / "config.toml").write_text(
        '[wiki]\ndomain = "Test"\n[server]\nport = 7070\n'
        '[[schedule.jobs]]\nop = "lint"\ncron = "0 0 * * *"\n',
        encoding="utf-8",
    )
    mock_sched = MagicMock()
    mock_sched.apply.return_value = ["sched-002"]
    with patch("synthadoc.core.scheduler.Scheduler", return_value=mock_sched):
        result = runner.invoke(app, ["schedule", "apply", "--wiki", str(wiki)])
    assert result.exit_code == 0, result.output
    assert "sched-002" in result.output
