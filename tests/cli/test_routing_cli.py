# Copyright (c) 2026 William Johnason / axoviq.com
from pathlib import Path
from typer.testing import CliRunner
from synthadoc.cli.main import app

runner = CliRunner()

INDEX_MD = """---
title: Index
---
## People
- [[alan-turing]]
- [[grace-hopper]]

## Hardware
- [[von-neumann-architecture]]
"""

ROUTING_WITH_DANGLING = """## People
- [[alan-turing]]
- [[deleted-page]]
"""


def _make_wiki(tmp_path: Path) -> Path:
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "index.md").write_text(INDEX_MD)
    (wiki / "alan-turing.md").write_text("---\ntitle: Alan Turing\n---\n")
    (wiki / "grace-hopper.md").write_text("---\ntitle: Grace Hopper\n---\n")
    (wiki / "von-neumann-architecture.md").write_text("---\ntitle: Von Neumann\n---\n")
    return tmp_path


def test_routing_init_creates_routing_md(tmp_path):
    w = _make_wiki(tmp_path)
    result = runner.invoke(app, ["routing", "init", "--wiki-root", str(w)])
    assert result.exit_code == 0, result.output
    routing = w / "ROUTING.md"
    assert routing.exists()
    content = routing.read_text()
    assert "## People" in content
    assert "[[alan-turing]]" in content


def test_routing_init_skips_if_exists(tmp_path):
    w = _make_wiki(tmp_path)
    (w / "ROUTING.md").write_text("## People\n")
    result = runner.invoke(app, ["routing", "init", "--wiki-root", str(w)])
    assert result.exit_code != 0
    assert "already exists" in result.output


def test_routing_validate_reports_dangling(tmp_path):
    w = _make_wiki(tmp_path)
    (w / "ROUTING.md").write_text(ROUTING_WITH_DANGLING)
    result = runner.invoke(app, ["routing", "validate", "--wiki-root", str(w)])
    assert result.exit_code == 0, result.output
    assert "deleted-page" in result.output


def test_routing_validate_clean_reports_ok(tmp_path):
    w = _make_wiki(tmp_path)
    (w / "ROUTING.md").write_text("## People\n- [[alan-turing]]\n")
    result = runner.invoke(app, ["routing", "validate", "--wiki-root", str(w)])
    assert result.exit_code == 0
    assert "clean" in result.output


def test_routing_clean_removes_dangling(tmp_path):
    w = _make_wiki(tmp_path)
    (w / "ROUTING.md").write_text(ROUTING_WITH_DANGLING)
    result = runner.invoke(app, ["routing", "clean", "--wiki-root", str(w)])
    assert result.exit_code == 0, result.output
    content = (w / "ROUTING.md").read_text()
    assert "deleted-page" not in content
    assert "alan-turing" in content


def test_routing_clean_nothing_to_remove(tmp_path):
    w = _make_wiki(tmp_path)
    (w / "ROUTING.md").write_text("## People\n- [[alan-turing]]\n")
    result = runner.invoke(app, ["routing", "clean", "--wiki-root", str(w)])
    assert result.exit_code == 0
    assert "nothing to remove" in result.output
