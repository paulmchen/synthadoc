# Copyright (c) 2026 William Johnason / axoviq.com
from pathlib import Path
import pytest
from synthadoc.core.routing import RoutingIndex

SAMPLE = """
## People
- [[alan-turing]]
- [[grace-hopper]]

## Hardware
- [[von-neumann-architecture]]
"""

def test_parse_branches(tmp_path):
    f = tmp_path / "ROUTING.md"
    f.write_text(SAMPLE)
    ri = RoutingIndex.parse(f)
    assert set(ri.branches.keys()) == {"People", "Hardware"}
    assert "alan-turing" in ri.branches["People"]
    assert "von-neumann-architecture" in ri.branches["Hardware"]

def test_validate_dangling(tmp_path):
    f = tmp_path / "ROUTING.md"
    f.write_text(SAMPLE)
    ri = RoutingIndex.parse(f)
    existing = {"alan-turing", "grace-hopper"}  # von-neumann-architecture missing
    dangling = ri.validate(existing)
    assert dangling == [("Hardware", "von-neumann-architecture")]

def test_clean_removes_dangling(tmp_path):
    f = tmp_path / "ROUTING.md"
    f.write_text(SAMPLE)
    ri = RoutingIndex.parse(f)
    existing = {"alan-turing", "grace-hopper"}
    removed = ri.clean(existing)
    assert removed == [("Hardware", "von-neumann-architecture")]
    assert "von-neumann-architecture" not in ri.branches.get("Hardware", [])

def test_save_round_trip(tmp_path):
    f = tmp_path / "ROUTING.md"
    f.write_text(SAMPLE)
    ri = RoutingIndex.parse(f)
    ri.clean({"alan-turing", "grace-hopper"})
    ri.save(f)
    content = f.read_text()
    assert "[[von-neumann-architecture]]" not in content
    assert "[[alan-turing]]" in content

def test_add_slug(tmp_path):
    f = tmp_path / "ROUTING.md"
    f.write_text(SAMPLE)
    ri = RoutingIndex.parse(f)
    ri.add_slug("ada-lovelace", "People")
    assert "ada-lovelace" in ri.branches["People"]

def test_parse_missing_file_returns_empty(tmp_path):
    ri = RoutingIndex.parse(tmp_path / "ROUTING.md")
    assert ri.branches == {}

def test_slugs_for_branches(tmp_path):
    f = tmp_path / "ROUTING.md"
    f.write_text(SAMPLE)
    ri = RoutingIndex.parse(f)
    slugs = ri.slugs_for_branches(["People"])
    assert "alan-turing" in slugs
    assert "von-neumann-architecture" not in slugs

def test_validate_reports_cross_branch_duplicate(tmp_path):
    duplicate = """
## People
- [[alan-turing]]
- [[grace-hopper]]

## Hardware
- [[alan-turing]]
- [[von-neumann-architecture]]
"""
    f = tmp_path / "ROUTING.md"
    f.write_text(duplicate)
    ri = RoutingIndex.parse(f)
    existing = {"alan-turing", "grace-hopper", "von-neumann-architecture"}
    issues = ri.validate(existing)
    assert len(issues) == 1
    branch, msg = issues[0]
    assert branch == "Hardware"
    assert "alan-turing" in msg
    assert "duplicate" in msg


def test_from_index_md_parses_branches(tmp_path):
    index = tmp_path / "index.md"
    index.write_text(
        "## People\n- [[alan-turing]]\n- [[grace-hopper]]\n\n"
        "## Hardware\n- [[von-neumann-architecture]]\n\n"
        "## Recently Added\n- [[recent-page]]\n\n"
        "## Index\n- [[index-entry]]\n",
        encoding="utf-8",
    )
    ri = RoutingIndex.from_index_md(index)
    assert set(ri.branches.keys()) == {"People", "Hardware"}
    assert "alan-turing" in ri.branches["People"]
    assert "grace-hopper" in ri.branches["People"]
    assert "von-neumann-architecture" in ri.branches["Hardware"]
    assert "Recently Added" not in ri.branches
    assert "Index" not in ri.branches
