# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest
from unittest.mock import AsyncMock, patch


def test_mcp_server_has_required_tools(tmp_wiki):
    from synthadoc.integration.mcp_server import create_mcp_server
    mcp = create_mcp_server(wiki_root=tmp_wiki)
    # _tool_manager.list_tools() is synchronous and returns Tool objects with .name
    tool_names = [t.name for t in mcp._tool_manager.list_tools()]
    for expected in ("synthadoc_ingest", "synthadoc_query", "synthadoc_lint",
                     "synthadoc_search", "synthadoc_status"):
        assert expected in tool_names


@pytest.mark.asyncio
async def test_mcp_query_tool_returns_answer(tmp_wiki):
    from synthadoc.integration.mcp_server import create_mcp_server
    from synthadoc.agents.query_agent import QueryResult
    mcp = create_mcp_server(wiki_root=tmp_wiki)
    mock_result = QueryResult(question="q", answer="the answer", citations=["p1"])
    with patch("synthadoc.core.orchestrator.Orchestrator.query",
               new=AsyncMock(return_value=mock_result)):
        # Use convert_result=False to get the raw dict back
        result = await mcp._tool_manager.call_tool(
            "synthadoc_query", {"question": "What is AI?"}, convert_result=False
        )
    assert result["answer"] == "the answer"


@pytest.mark.asyncio
async def test_mcp_ingest_tool_returns_job_id(tmp_wiki):
    from synthadoc.integration.mcp_server import create_mcp_server
    mcp = create_mcp_server(wiki_root=tmp_wiki)
    with patch("synthadoc.core.orchestrator.Orchestrator.ingest",
               new=AsyncMock(return_value="job-xyz")):
        result = await mcp._tool_manager.call_tool(
            "synthadoc_ingest", {"source": "paper.pdf"}, convert_result=False
        )
    assert result["job_id"] == "job-xyz"


@pytest.mark.asyncio
async def test_mcp_lint_tool_returns_result(tmp_wiki):
    from unittest.mock import MagicMock
    from synthadoc.integration.mcp_server import create_mcp_server
    mcp = create_mcp_server(wiki_root=tmp_wiki)
    mock_report = MagicMock()
    mock_report.contradictions_found = 2
    mock_report.orphan_slugs = ["orphan-page"]
    with patch("synthadoc.core.orchestrator.Orchestrator.lint",
               new=AsyncMock(return_value=mock_report)):
        result = await mcp._tool_manager.call_tool(
            "synthadoc_lint", {"scope": "all"}, convert_result=False
        )
    assert result["contradictions_found"] == 2
    assert "orphan-page" in result["orphans"]


@pytest.mark.asyncio
async def test_mcp_search_tool_returns_results(tmp_wiki):
    from unittest.mock import MagicMock
    from synthadoc.integration.mcp_server import create_mcp_server
    mcp = create_mcp_server(wiki_root=tmp_wiki)
    mock_hit = MagicMock()
    mock_hit.slug = "test-page"
    mock_hit.score = 0.9
    mock_hit.title = "Test Page"
    mock_hit.snippet = "test excerpt"
    with patch("synthadoc.storage.search.HybridSearch.bm25_search",
               return_value=[mock_hit]):
        result = await mcp._tool_manager.call_tool(
            "synthadoc_search", {"terms": "test query"}, convert_result=False
        )
    assert len(result["results"]) == 1
    assert result["results"][0]["slug"] == "test-page"


@pytest.mark.asyncio
async def test_mcp_status_tool_returns_page_count(tmp_wiki):
    from synthadoc.integration.mcp_server import create_mcp_server
    mcp = create_mcp_server(wiki_root=tmp_wiki)
    with patch("synthadoc.storage.wiki.WikiStorage.list_pages",
               return_value=["page-1", "page-2"]):
        result = await mcp._tool_manager.call_tool(
            "synthadoc_status", {}, convert_result=False
        )
    assert result["pages"] == 2
