# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
"""
Synthetic routing benchmark — BM25 query latency with routing-scoped search.

Run with:
  pytest tests/performance/test_routing_benchmark.py -m benchmark -v

SLA targets (P95):
  100 pages  < 200ms
  500 pages  < 300ms
  1000 pages < 500ms
"""
import asyncio
from pathlib import Path
import pytest

from synthadoc.core.routing import RoutingIndex
from synthadoc.storage.search import HybridSearch
from synthadoc.storage.wiki import WikiStorage


def _make_synthetic_wiki(tmp_path: Path, page_count: int,
                          branch_count: int = 10) -> tuple[Path, RoutingIndex]:
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    branches: dict[str, list[str]] = {f"Branch{i}": [] for i in range(branch_count)}

    for i in range(page_count):
        slug = f"page-{i:04d}"
        branch = f"Branch{i % branch_count}"
        branches[branch].append(slug)
        content = (
            f"---\ntitle: Page {i}\ntags: [tag{i % 20}]\nstatus: active\n"
            f"confidence: high\nsources: []\n---\n\n"
            + f"This is page {i} about topic {i % 50}. " * 20
        )
        (wiki_dir / f"{slug}.md").write_text(content, encoding="utf-8")

    routing_path = tmp_path / "ROUTING.md"
    ri = RoutingIndex(branches)
    ri.save(routing_path)
    return wiki_dir, ri


@pytest.mark.benchmark
@pytest.mark.parametrize("page_count", [100, 500, 1000, 10000])
def test_bm25_query_latency_with_routing(benchmark, tmp_path, page_count):
    """BM25 query latency with routing-scoped search at 100/500/1000 pages."""
    wiki_dir, ri = _make_synthetic_wiki(tmp_path, page_count)
    scoped_slugs = ri.slugs_for_branches(["Branch0", "Branch1"])

    store = WikiStorage(wiki_dir)
    search = HybridSearch(store=store, index_path=tmp_path / "search.db")

    def sync_run():
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                search.hybrid_search(
                    ["topic", "computation", "history"],
                    top_n=8,
                    scoped_slugs=scoped_slugs,
                )
            )
        finally:
            loop.close()

    result = benchmark(sync_run)
    assert isinstance(result, list)


@pytest.mark.benchmark
@pytest.mark.parametrize("page_count", [100, 500, 1000, 10000])
def test_bm25_query_latency_full_corpus(benchmark, tmp_path, page_count):
    """BM25 query latency without scoping — baseline comparison."""
    wiki_dir, _ = _make_synthetic_wiki(tmp_path, page_count)

    store = WikiStorage(wiki_dir)
    search = HybridSearch(store=store, index_path=tmp_path / "search.db")

    def sync_run():
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                search.hybrid_search(
                    ["topic", "computation", "history"],
                    top_n=8,
                )
            )
        finally:
            loop.close()

    result = benchmark(sync_run)
    assert isinstance(result, list)
