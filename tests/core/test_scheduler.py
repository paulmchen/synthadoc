# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import platform
import pytest
from unittest.mock import MagicMock, patch
from synthadoc.core.scheduler import Scheduler, ScheduleEntry


def test_schedule_entry_parses_cron():
    entry = ScheduleEntry(op="lint", cron="0 3 * * 0", wiki="research")
    assert entry.op == "lint"
    assert entry.cron == "0 3 * * 0"


def test_scheduler_add_returns_id():
    sched = Scheduler(wiki="research", wiki_root="/tmp/wiki")
    with patch.object(sched, "_register_os_task", return_value="sched-001"):
        entry_id = sched.add(op="lint", cron="0 3 * * 0")
    assert entry_id.startswith("sched-")


def test_scheduler_list_returns_registered_entries():
    sched = Scheduler(wiki="research", wiki_root="/tmp/wiki")
    with patch.object(sched, "_list_os_tasks", return_value=[
        ScheduleEntry(id="s1", op="lint", cron="0 3 * * 0", wiki="research"),
    ]):
        entries = sched.list()
    assert len(entries) == 1
    assert entries[0].op == "lint"


def test_scheduler_remove_calls_os():
    sched = Scheduler(wiki="research", wiki_root="/tmp/wiki")
    with patch.object(sched, "_remove_os_task") as mock_remove:
        sched.remove("sched-001")
    mock_remove.assert_called_once_with("sched-001")


@pytest.mark.skipif(platform.system() != "Linux", reason="crontab only on Linux/macOS")
def test_scheduler_linux_generates_crontab_entry(tmp_path):
    sched = Scheduler(wiki="research", wiki_root=str(tmp_path))
    line = sched._build_crontab_line(op="lint", cron="0 3 * * 0", entry_id="s1")
    assert "0 3 * * 0" in line
    assert "synthadoc" in line
    assert "lint" in line
    assert "# synthadoc:s1" in line


@pytest.mark.skipif(platform.system() != "Windows", reason="schtasks only on Windows")
def test_scheduler_windows_generates_schtasks_args(tmp_path):
    sched = Scheduler(wiki="research", wiki_root=str(tmp_path))
    args = sched._build_schtasks_args(op="lint", cron="0 3 * * 0", entry_id="s1")
    assert "/TN" in args
    assert "synthadoc-s1" in " ".join(args)


_CRONTAB_OUTPUT = (
    "# other line\n"
    "0 2 * * * synthadoc -w my-wiki lint run # synthadoc:sched-abc123\n"
    "30 14 * * * synthadoc -w my-wiki ingest run # synthadoc:sched-def456\n"
)


def test_list_crontab_parses_tagged_lines():
    sched = Scheduler(wiki="my-wiki", wiki_root="/wikis/my-wiki")
    with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout=_CRONTAB_OUTPUT)):
        entries = sched._list_crontab()
    assert len(entries) == 2
    assert {e.id for e in entries} == {"sched-abc123", "sched-def456"}


def test_list_crontab_empty_crontab():
    sched = Scheduler(wiki="my-wiki", wiki_root="/wikis/my-wiki")
    with patch("subprocess.run", return_value=MagicMock(returncode=1, stdout="")):
        entries = sched._list_crontab()
    assert entries == []


def test_list_crontab_no_synthadoc_lines():
    sched = Scheduler(wiki="my-wiki", wiki_root="/wikis/my-wiki")
    with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="0 5 * * * /usr/bin/backup\n")):
        entries = sched._list_crontab()
    assert entries == []


_SCHTASKS_OUTPUT = (
    "TaskName:                             \\synthadoc-sched-win1\n"
    "Task To Run:                          synthadoc -w my-wiki lint run\n"
    "\n"
    "TaskName:                             \\other-task\n"
    "Task To Run:                          notepad.exe\n"
)


def test_list_schtasks_parses_entries():
    sched = Scheduler(wiki="my-wiki", wiki_root="/wikis/my-wiki")
    with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout=_SCHTASKS_OUTPUT)):
        entries = sched._list_schtasks()
    assert len(entries) == 1
    assert entries[0].id == "sched-win1"


def test_add_crontab_entry_calls_subprocess():
    sched = Scheduler(wiki="my-wiki", wiki_root="/wikis/my-wiki")
    mock_run = MagicMock(return_value=MagicMock(returncode=0, stdout=""))
    with patch("subprocess.run", mock_run):
        sched._add_crontab_entry(op="lint run", cron="0 2 * * *", entry_id="sched-001")
    assert mock_run.call_count == 2  # crontab -l, then crontab -


def test_apply_returns_ids():
    sched = Scheduler(wiki="my-wiki", wiki_root="/wikis/my-wiki")
    with patch.object(sched, "add", side_effect=lambda op, cron: f"sched-{op[:4]}"):
        jobs = [
            ScheduleEntry(op="lint run", cron="0 2 * * *", wiki="my-wiki"),
            ScheduleEntry(op="ingest run", cron="0 3 * * *", wiki="my-wiki"),
        ]
        ids = sched.apply(jobs)
    assert len(ids) == 2


def test_build_schtasks_args_zero_padded():
    sched = Scheduler(wiki="my-wiki", wiki_root="/wikis/my-wiki")
    args = sched._build_schtasks_args(op="lint run", cron="5 9 * * *", entry_id="sched-001")
    assert "09:05" in args


def test_scheduler_apply_from_config(tmp_path):
    """schedule apply registers all jobs declared in config.toml."""
    from synthadoc.config import load_config
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        '[agents]\ndefault = { provider = "anthropic", model = "claude-opus-4-6" }\n'
        '[[schedule.jobs]]\nop = "lint"\ncron = "0 3 * * 0"\n'
        '[[schedule.jobs]]\nop = "ingest --batch raw_sources/"\ncron = "0 2 * * *"\n'
    )
    cfg = load_config(project_config=cfg_file)
    assert len(cfg.schedule.jobs) == 2
    assert cfg.schedule.jobs[0].op == "lint"
    assert cfg.schedule.jobs[1].cron == "0 2 * * *"
