# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest
from typer.testing import CliRunner
from unittest.mock import AsyncMock, patch, MagicMock
from synthadoc.cli.main import app

runner = CliRunner()


def test_ingest_batch_dir(tmp_path):
    """--batch scans directory for supported files and enqueues each."""
    (tmp_path / "a.md").write_text("# A", encoding="utf-8")
    (tmp_path / "b.pdf").write_bytes(b"%PDF-1.4 dummy")
    (tmp_path / "skip.xyz").write_text("ignored")
    # ingest.py is a thin HTTP client — patch the post() helper it imports
    with patch("synthadoc.cli.ingest.post", return_value={"job_id": "job-1"}) as mock_post:
        result = runner.invoke(app, ["ingest", "--batch", str(tmp_path)])
    assert result.exit_code == 0
    assert mock_post.call_count == 2    # a.md + b.pdf, not skip.xyz


def test_ingest_manifest_file(tmp_path):
    """--file reads a manifest and enqueues each listed path."""
    doc = tmp_path / "doc.md"
    doc.write_text("# Doc", encoding="utf-8")
    manifest = tmp_path / "sources.txt"
    manifest.write_text(str(doc) + "\n", encoding="utf-8")
    with patch("synthadoc.cli.ingest.post", return_value={"job_id": "job-1"}) as mock_post:
        result = runner.invoke(app, ["ingest", "--file", str(manifest)])
    assert result.exit_code == 0
    assert mock_post.call_count == 1


def test_ingest_manifest_urls_not_mangled(tmp_path):
    """URLs in a manifest file must be passed through unchanged — not resolved as paths."""
    manifest = tmp_path / "sources.txt"
    manifest.write_text("https://en.wikipedia.org/wiki/Alan_Turing\n", encoding="utf-8")
    with patch("synthadoc.cli.ingest.post", return_value={"job_id": "job-1"}) as mock_post:
        result = runner.invoke(app, ["ingest", "--file", str(manifest)])
    assert result.exit_code == 0
    payload = mock_post.call_args[0][2]
    assert payload["source"] == "https://en.wikipedia.org/wiki/Alan_Turing"


def test_ingest_manifest_skips_blanks_and_comments(tmp_path):
    """Blank lines and # comment lines in a manifest are silently skipped."""
    doc = tmp_path / "doc.md"
    doc.write_text("# Doc", encoding="utf-8")
    manifest = tmp_path / "sources.txt"
    manifest.write_text(
        f"# this is a comment\n\n{doc}\n\n# another comment\n",
        encoding="utf-8",
    )
    with patch("synthadoc.cli.ingest.post", return_value={"job_id": "job-1"}) as mock_post:
        result = runner.invoke(app, ["ingest", "--file", str(manifest)])
    assert result.exit_code == 0
    assert mock_post.call_count == 1   # only doc.md, not blanks or comments


def test_ingest_force_bypasses_dedup(tmp_path):
    """--force sets force=True in the HTTP payload sent to the server."""
    source = tmp_path / "doc.md"
    source.write_text("# Doc", encoding="utf-8")
    with patch("synthadoc.cli.ingest.post", return_value={"job_id": "job-1"}) as mock_post:
        result = runner.invoke(app, ["ingest", str(source), "--force"])
    assert result.exit_code == 0
    # post(wiki, path, payload) — payload is the third positional arg
    payload = mock_post.call_args[0][2]
    assert payload.get("force") is True


def test_jobs_list_filtered_by_dead_status(tmp_path):
    """jobs list --status dead returns only dead jobs."""
    # jobs_list is an HTTP client — patch the get() helper imported at module level
    with patch("synthadoc.cli.jobs.get", return_value=[
        {"id": "a1", "status": "dead", "operation": "ingest", "created_at": None}
    ]):
        result = runner.invoke(app, ["jobs", "list", "--status", "dead"])
    assert result.exit_code == 0
    assert "a1" in result.output


def test_jobs_retry_dead_reenqueues(tmp_path):
    """jobs retry <id> resets the job to pending via Orchestrator.queue.retry()."""
    # jobs_retry uses an inline import from synthadoc.core.orchestrator
    with patch("synthadoc.core.orchestrator.Orchestrator") as MockOrch:
        mock_orch = AsyncMock()
        mock_orch.queue.retry = AsyncMock()
        MockOrch.return_value = mock_orch
        result = runner.invoke(app, ["jobs", "retry", "a1", "--wiki", str(tmp_path)])
    assert result.exit_code == 0
    mock_orch.queue.retry.assert_called_once_with("a1")


def test_jobs_purge_older_than(tmp_path):
    """jobs purge --older-than 30 removes stale jobs."""
    with patch("synthadoc.core.orchestrator.Orchestrator") as MockOrch:
        mock_orch = AsyncMock()
        mock_orch.queue.purge = AsyncMock(return_value=5)
        MockOrch.return_value = mock_orch
        result = runner.invoke(app, ["jobs", "purge", "--older-than", "30",
                                     "--wiki", str(tmp_path)])
    assert result.exit_code == 0
    mock_orch.queue.purge.assert_called_once_with(older_than_days=30)


import asyncio as _asyncio


def test_cache_clear_removes_entries(tmp_path):
    """cache clear deletes all LLM response cache entries and reports count."""
    import asyncio
    from synthadoc.core.cache import CacheManager

    # Populate the cache with 3 entries
    sd = tmp_path / ".synthadoc"
    sd.mkdir()

    async def _seed():
        cm = CacheManager(sd / "cache.db")
        await cm.init()
        await cm.set("k1", {"v": 1})
        await cm.set("k2", {"v": 2})
        await cm.set("k3", {"v": 3})

    asyncio.run(_seed())

    result = runner.invoke(app, ["cache", "clear", "--wiki", str(tmp_path)])
    assert result.exit_code == 0
    assert "3" in result.output
    assert "removed" in result.output.lower()


def test_cache_clear_no_db_reports_nothing(tmp_path):
    """cache clear on a wiki with no cache.db exits cleanly with an informational message."""
    result = runner.invoke(app, ["cache", "clear", "--wiki", str(tmp_path)])
    assert result.exit_code == 0
    assert "nothing" in result.output.lower() or "no cache" in result.output.lower()


def test_cache_clear_unknown_action_exits_nonzero(tmp_path):
    result = runner.invoke(app, ["cache", "bogus"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# install + LLM scaffold
# ---------------------------------------------------------------------------

def test_install_fresh_wiki_calls_scaffold_agent(tmp_path):
    """install must call ScaffoldAgent when API key is available."""
    from synthadoc.agents.scaffold_agent import ScaffoldResult
    import synthadoc.cli.install as install_mod

    mock_result = ScaffoldResult(
        index_md="---\ntitle: Index\n---\n# Test Index\n",
        agents_md="# AGENTS.md — Robotics Wiki\n",
        purpose_md="# Wiki Purpose\nThis wiki covers: Robotics.\n",
        dashboard_intro="A wiki tracking Robotics knowledge.",
    )

    with patch("synthadoc.cli.install._run_scaffold", return_value=mock_result) as mock_scaffold, \
         patch("synthadoc.cli.install._find_free_port", return_value=7070):
        with patch.object(install_mod, "_REGISTRY", tmp_path / "wikis.json"):
            result = runner.invoke(app, [
                "install", "test-wiki",
                "--target", str(tmp_path),
                "--domain", "Robotics",
            ])

    assert result.exit_code == 0, result.output
    mock_scaffold.assert_called_once()


def test_install_fresh_wiki_falls_back_when_no_api_key(tmp_path):
    """install must fall back to static templates when scaffold returns None."""
    import synthadoc.cli.install as install_mod

    with patch("synthadoc.cli.install._run_scaffold", return_value=None), \
         patch("synthadoc.cli.install._find_free_port", return_value=7070):
        with patch.object(install_mod, "_REGISTRY", tmp_path / "wikis.json"):
            result = runner.invoke(app, [
                "install", "test-wiki2",
                "--target", str(tmp_path),
                "--domain", "Physics",
            ])

    assert result.exit_code == 0, result.output
    # Static index.md fallback must still be written
    assert (tmp_path / "test-wiki2" / "wiki" / "index.md").exists()
    # Hint message must appear
    assert "scaffold" in result.output.lower()
