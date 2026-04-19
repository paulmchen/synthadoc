# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest
from typer.testing import CliRunner
from synthadoc.cli.main import app
from synthadoc.cli.lint import _parse_frontmatter, _index_suggestion

runner = CliRunner()


# ---------------------------------------------------------------------------
# _parse_frontmatter
# ---------------------------------------------------------------------------

def test_parse_frontmatter_valid():
    text = "---\ntitle: My Page\ntags: [foo, bar]\nstatus: active\n---\n\nbody"
    fm = _parse_frontmatter(text)
    assert fm["title"] == "My Page"
    assert fm["tags"] == ["foo", "bar"]


def test_parse_frontmatter_missing():
    assert _parse_frontmatter("no frontmatter here") == {}


def test_parse_frontmatter_invalid_yaml():
    text = "---\n: bad: yaml: [\n---\nbody"
    assert _parse_frontmatter(text) == {}


# ---------------------------------------------------------------------------
# _index_suggestion
# ---------------------------------------------------------------------------

def test_index_suggestion_with_tags():
    result = _index_suggestion("alan-turing", {"title": "Alan Turing", "tags": ["pioneer", "ai"]})
    assert "[[alan-turing]]" in result
    assert "pioneer" in result


def test_index_suggestion_without_tags():
    result = _index_suggestion("alan-turing", {})
    assert "[[alan-turing]]" in result
    assert "Alan Turing" in result


def test_index_suggestion_title_fallback():
    result = _index_suggestion("von-neumann", {"title": "Von Neumann"})
    assert "Von Neumann" in result


# ---------------------------------------------------------------------------
# lint report command (reads files directly, no server required)
# ---------------------------------------------------------------------------

def _make_wiki(tmp_path, pages: dict[str, str]):
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    for name, content in pages.items():
        (wiki_dir / f"{name}.md").write_text(content, encoding="utf-8")
    import synthadoc.cli.install as install_mod
    return wiki_dir, tmp_path


def test_lint_report_all_clear(tmp_path, monkeypatch):
    import synthadoc.cli.install as install_mod
    wiki_dir, root = _make_wiki(tmp_path, {
        "index": "# Index\n\n[[topic-a]]",
        "topic-a": "---\nstatus: active\n---\n\n# Topic A",
    })
    monkeypatch.setattr(install_mod, "_REGISTRY",
                        tmp_path / "wikis.json")
    monkeypatch.setattr(install_mod, "_read_registry",
                        lambda: {"mywiki": {"path": str(tmp_path)}})
    result = runner.invoke(app, ["lint", "report", "-w", "mywiki"])
    assert result.exit_code == 0, result.output
    assert "All clear" in result.output


def test_lint_report_contradicted(tmp_path, monkeypatch):
    import synthadoc.cli.install as install_mod
    wiki_dir, root = _make_wiki(tmp_path, {
        "index": "# Index\n",
        "bad-page": "---\nstatus: contradicted\n---\n# Bad",
    })
    monkeypatch.setattr(install_mod, "_read_registry",
                        lambda: {"mywiki": {"path": str(tmp_path)}})
    result = runner.invoke(app, ["lint", "report", "-w", "mywiki"])
    assert result.exit_code == 0, result.output
    assert "bad-page" in result.output
    assert "contradiction" in result.output.lower()


def test_lint_report_orphan(tmp_path, monkeypatch):
    import synthadoc.cli.install as install_mod
    wiki_dir, root = _make_wiki(tmp_path, {
        "index": "# Index\n",
        "orphan-page": "---\nstatus: active\n---\n# Orphan",
    })
    monkeypatch.setattr(install_mod, "_read_registry",
                        lambda: {"mywiki": {"path": str(tmp_path)}})
    result = runner.invoke(app, ["lint", "report", "-w", "mywiki"])
    assert result.exit_code == 0, result.output
    assert "orphan-page" in result.output
    assert "orphan" in result.output.lower()


def test_lint_report_missing_wiki_dir(tmp_path, monkeypatch):
    import synthadoc.cli.install as install_mod
    monkeypatch.setattr(install_mod, "_read_registry",
                        lambda: {"mywiki": {"path": str(tmp_path)}})
    result = runner.invoke(app, ["lint", "report", "-w", "mywiki"])
    assert result.exit_code != 0
