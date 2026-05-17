# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest
from unittest.mock import patch
from typer.testing import CliRunner
from synthadoc.cli.main import app

runner = CliRunner()


def _make_wiki(tmp_path, domain="Robotics"):
    """Create a minimal wiki directory layout."""
    wiki_dir = tmp_path / "my-wiki"
    (wiki_dir / "wiki").mkdir(parents=True)
    (wiki_dir / ".synthadoc").mkdir()
    (wiki_dir / ".synthadoc" / "config.toml").write_text(
        f'[wiki]\ndomain = "{domain}"\n[server]\nport = 7070\n',
        encoding="utf-8",
    )
    (wiki_dir / "wiki" / "index.md").write_text(
        "# Index\n\n## Key Concepts\n<!-- desc -->\n",
        encoding="utf-8",
    )
    (wiki_dir / "wiki" / "purpose.md").write_text(
        f"# Wiki Purpose\n\nThis wiki covers: {domain}.\n",
        encoding="utf-8",
    )
    (wiki_dir / "AGENTS.md").write_text(
        f"# AGENTS.md — {domain} Wiki\n",
        encoding="utf-8",
    )
    return wiki_dir


def test_scaffold_command_writes_files(tmp_path):
    """scaffold rewrites index.md, AGENTS.md, and purpose.md from LLM output."""
    from synthadoc.agents.scaffold_agent import ScaffoldResult
    wiki_dir = _make_wiki(tmp_path)

    mock_result = ScaffoldResult(
        index_md="---\ntitle: Index\n---\n# Robotics — Index\n",
        agents_md="# AGENTS.md — Robotics Wiki\n",
        purpose_md="# Wiki Purpose\nThis wiki covers: Robotics.\n",
        dashboard_intro="A wiki tracking Robotics knowledge.",
    )

    with patch("synthadoc.cli.scaffold._run_scaffold", return_value=mock_result):
        result = runner.invoke(app, ["scaffold", "--wiki", str(wiki_dir)])

    assert result.exit_code == 0, result.output
    assert (wiki_dir / "wiki" / "index.md").read_text(encoding="utf-8") == mock_result.index_md
    assert (wiki_dir / "AGENTS.md").read_text(encoding="utf-8") == mock_result.agents_md
    assert (wiki_dir / "wiki" / "purpose.md").read_text(encoding="utf-8") == mock_result.purpose_md


def test_scaffold_detects_protected_slugs(tmp_path):
    """scaffold passes slugs of existing linked pages to the LLM call."""
    from synthadoc.agents.scaffold_agent import ScaffoldResult
    wiki_dir = _make_wiki(tmp_path)

    # Create a real page that is linked from index.md
    (wiki_dir / "wiki" / "neural-networks.md").write_text("# Neural Networks\n", encoding="utf-8")
    (wiki_dir / "wiki" / "index.md").write_text(
        "# Index\n\n## Key Concepts\n[[neural-networks]]\n",
        encoding="utf-8",
    )

    mock_result = ScaffoldResult(
        index_md="---\ntitle: Index\n---\n# Robotics — Index\n",
        agents_md="# AGENTS.md\n",
        purpose_md="# Purpose\n",
        dashboard_intro="desc",
    )

    captured_slugs = []

    def _capture_scaffold(dest, domain, protected_slugs=None):
        captured_slugs.extend(protected_slugs or [])
        return mock_result

    with patch("synthadoc.cli.scaffold._run_scaffold", side_effect=_capture_scaffold):
        result = runner.invoke(app, ["scaffold", "--wiki", str(wiki_dir)])

    assert result.exit_code == 0, result.output
    assert "neural-networks" in captured_slugs


def test_scaffold_does_not_touch_config(tmp_path):
    """scaffold must never modify .synthadoc/config.toml."""
    from synthadoc.agents.scaffold_agent import ScaffoldResult
    wiki_dir = _make_wiki(tmp_path)
    config_path = wiki_dir / ".synthadoc" / "config.toml"
    original_config = config_path.read_text(encoding="utf-8")

    mock_result = ScaffoldResult(
        index_md="# Index\n",
        agents_md="# AGENTS\n",
        purpose_md="# Purpose\n",
        dashboard_intro="desc",
    )

    with patch("synthadoc.cli.scaffold._run_scaffold", return_value=mock_result):
        result = runner.invoke(app, ["scaffold", "--wiki", str(wiki_dir)])

    assert result.exit_code == 0, result.output
    assert config_path.read_text(encoding="utf-8") == original_config


def test_scaffold_exits_when_scaffold_fails(tmp_path):
    """scaffold exits non-zero when the LLM call returns None (no API key)."""
    wiki_dir = _make_wiki(tmp_path)

    with patch("synthadoc.cli.scaffold._run_scaffold", return_value=None):
        result = runner.invoke(app, ["scaffold", "--wiki", str(wiki_dir)])

    assert result.exit_code != 0


def test_scaffold_missing_wiki_dir_exits(tmp_path):
    """scaffold exits non-zero when the wiki directory does not exist."""
    nonexistent = tmp_path / "no-such-wiki"
    result = runner.invoke(app, ["scaffold", "--wiki", str(nonexistent)])
    assert result.exit_code != 0


def test_scaffold_missing_config_exits(tmp_path):
    """scaffold exits non-zero when config.toml is absent."""
    wiki_dir = tmp_path / "bare-wiki"
    (wiki_dir / "wiki").mkdir(parents=True)
    result = runner.invoke(app, ["scaffold", "--wiki", str(wiki_dir)])
    assert result.exit_code != 0


def test_protected_slugs_returns_linked_existing_pages(tmp_path):
    """_protected_slugs includes slugs that are both linked from index.md and have a wiki file."""
    from synthadoc.cli.scaffold import _protected_slugs
    (tmp_path / "wiki").mkdir()
    (tmp_path / "wiki" / "index.md").write_text(
        "# Index\n\n[[neural-networks]] and [[robotics]]\n",
        encoding="utf-8",
    )
    (tmp_path / "wiki" / "neural-networks.md").write_text("# NN\n", encoding="utf-8")
    # robotics.md does not exist — must not be included
    slugs = _protected_slugs(tmp_path)
    assert "neural-networks" in slugs
    assert "robotics" not in slugs


def test_protected_slugs_empty_when_no_index(tmp_path):
    """_protected_slugs returns [] when index.md is absent."""
    from synthadoc.cli.scaffold import _protected_slugs
    (tmp_path / "wiki").mkdir()
    slugs = _protected_slugs(tmp_path)
    assert slugs == []


def test_apply_categories_stamps_headings_on_pages(tmp_path):
    """_apply_categories reads H2 headings from index.md and stamps categories on linked pages."""
    from synthadoc.cli.scaffold import _apply_categories
    from synthadoc.storage.wiki import WikiStorage

    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    (wiki_dir / "neural-networks.md").write_text(
        "---\ntitle: Neural Networks\ntags: []\nstatus: active\n"
        "confidence: high\ncreated: '2026-01-01'\nsources: []\n---\nContent.",
        encoding="utf-8",
    )
    index_md = "# Index\n\n## Key Concepts\n- [[neural-networks]]\n"
    updated = _apply_categories(tmp_path, index_md)
    assert updated >= 1
    store = WikiStorage(wiki_dir)
    page = store.read_page("neural-networks")
    assert page is not None
    assert "Key Concepts" in (page.categories or [])
