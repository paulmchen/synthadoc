# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch


def test_health(tmp_wiki):
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        assert client.get("/health").json()["status"] == "ok"


def test_status_returns_page_count(tmp_wiki):
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        data = client.get("/status").json()
    assert "pages" in data


def test_query_endpoint(tmp_wiki):
    from synthadoc.integration.http_server import create_app
    from synthadoc.agents.query_agent import QueryResult
    app = create_app(wiki_root=tmp_wiki)
    mock = QueryResult(question="q", answer="answer", citations=["p1"])
    with patch("synthadoc.core.orchestrator.Orchestrator.query",
               new=AsyncMock(return_value=mock)):
        with TestClient(app) as client:
            resp = client.post("/query", json={"question": "What is AI?"})
    assert resp.json()["answer"] == "answer"


def test_ingest_endpoint_returns_job_id(tmp_wiki):
    """POST /jobs/ingest enqueues a job and returns its ID."""
    from synthadoc.integration.http_server import create_app
    app = create_app(wiki_root=tmp_wiki)
    # The endpoint calls queue.enqueue(), not orch.ingest() directly
    with patch("synthadoc.core.queue.JobQueue.enqueue",
               new=AsyncMock(return_value="job-abc")):
        with TestClient(app) as client:
            resp = client.post("/jobs/ingest", json={"source": "paper.pdf"})
    assert resp.status_code == 200
    assert resp.json()["job_id"] == "job-abc"


def test_lint_report_shows_contradictions_and_orphans(tmp_wiki):
    """GET /lint/report reads wiki files and returns contradicted pages and orphans."""
    wiki_dir = tmp_wiki / "wiki"
    # A page marked contradicted in its frontmatter
    (wiki_dir / "conflicted-page.md").write_text(
        "---\nstatus: contradicted\n---\n# Conflicted Page\n",
        encoding="utf-8",
    )
    # An orphan page — no other page links to it
    (wiki_dir / "orphan-page.md").write_text(
        "---\nstatus: active\ntags: [test]\n---\n# Orphan Page\n",
        encoding="utf-8",
    )
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.get("/lint/report")
    assert resp.status_code == 200
    data = resp.json()
    assert "conflicted-page" in data["contradictions"]
    assert "orphan-page" in data["orphans"]


def test_query_empty_question_returns_422(tmp_wiki):
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.post("/query", json={"question": ""})
    assert resp.status_code == 422


def test_ingest_url_not_mangled_to_file_path(tmp_wiki):
    """POST /jobs/ingest with an http URL must not be resolved as a local path."""
    from synthadoc.integration.http_server import create_app
    with patch("synthadoc.core.queue.JobQueue.enqueue",
               new=AsyncMock(return_value="job-url")) as mock_enqueue:
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.post("/jobs/ingest", json={"source": "https://example.com/article"})
    assert resp.status_code == 200
    queued_source = mock_enqueue.call_args[0][1]["source"]
    assert queued_source == "https://example.com/article"
    assert str(tmp_wiki) not in queued_source


def test_ingest_backslash_url_is_normalised_not_path_resolved(tmp_wiki):
    """POST /jobs/ingest with a Windows backslash URL must store a clean https:// URL.

    Users sometimes paste URLs as https:\\example.com\\path (backslashes).
    The endpoint must normalise these to forward slashes and NOT prepend the
    wiki root — otherwise the stored source becomes an unresolvable local path.
    """
    from synthadoc.integration.http_server import create_app
    backslash_url = r"https:\example.com\collections\page"
    with patch("synthadoc.core.queue.JobQueue.enqueue",
               new=AsyncMock(return_value="job-bs")) as mock_enqueue:
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.post("/jobs/ingest", json={"source": backslash_url})
    assert resp.status_code == 200
    queued_source = mock_enqueue.call_args[0][1]["source"]
    assert queued_source == "https://example.com/collections/page"
    assert str(tmp_wiki) not in queued_source


def test_retry_job_endpoint(tmp_wiki):
    """POST /jobs/{id}/retry resets the job to pending."""
    from synthadoc.integration.http_server import create_app
    from synthadoc.core.queue import Job, JobStatus
    fake_job = Job(id="dead-1", operation="ingest", payload={},
                   status=JobStatus.DEAD, retries=3, error="timeout")
    with patch("synthadoc.core.queue.JobQueue.list_jobs",
               new=AsyncMock(return_value=[fake_job])):
        with patch("synthadoc.core.queue.JobQueue.retry",
                   new=AsyncMock()) as mock_retry:
            with TestClient(create_app(wiki_root=tmp_wiki)) as client:
                resp = client.post("/jobs/dead-1/retry")
    assert resp.status_code == 200
    assert resp.json()["retried"] == "dead-1"
    mock_retry.assert_awaited_once_with("dead-1")


def test_audit_queries_returns_empty_initially(tmp_wiki):
    """GET /audit/queries must return an empty list before any queries are made."""
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.get("/audit/queries")
    assert resp.status_code == 200
    data = resp.json()
    assert data["records"] == []
    assert data["count"] == 0


def test_audit_queries_returns_recorded_data(tmp_wiki):
    """GET /audit/queries must return records after queries have been made."""
    import asyncio
    from synthadoc.integration.http_server import create_app
    from synthadoc.storage.log import AuditDB
    # Pre-populate the DB file before the server starts so it shares the record
    db = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    asyncio.run(db.init())
    asyncio.run(db.record_query(
        question="What is Moore's Law?", sub_questions_count=1,
        tokens=125, cost_usd=0.0004,
    ))
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.get("/audit/queries")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["records"][0]["question"] == "What is Moore's Law?"


def test_query_post_provider_unavailable_returns_502(tmp_wiki):
    """If the LLM provider raises a connection error, POST /query must return 502."""
    from synthadoc.integration.http_server import create_app
    with patch("synthadoc.core.orchestrator.Orchestrator.query",
               new=AsyncMock(side_effect=Exception("Connection refused"))):
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.post("/query", json={"question": "What is Moore's Law?"})
    assert resp.status_code == 502
    assert "unavailable" in resp.json()["detail"].lower()


def test_query_get_provider_unavailable_returns_502(tmp_wiki):
    """If the LLM provider raises, GET /query must also return 502."""
    from synthadoc.integration.http_server import create_app
    with patch("synthadoc.core.orchestrator.Orchestrator.query",
               new=AsyncMock(side_effect=Exception("timeout"))):
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.get("/query", params={"q": "test"})
    assert resp.status_code == 502
    assert "unavailable" in resp.json()["detail"].lower()


def test_retry_job_not_found(tmp_wiki):
    """POST /jobs/{id}/retry returns 404 for unknown job IDs."""
    from synthadoc.integration.http_server import create_app
    with patch("synthadoc.core.queue.JobQueue.list_jobs",
               new=AsyncMock(return_value=[])):
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.post("/jobs/nonexistent/retry")
    assert resp.status_code == 404


def test_purge_jobs_endpoint(tmp_wiki):
    """DELETE /jobs?older_than=N returns the count of purged jobs."""
    from synthadoc.integration.http_server import create_app
    with patch("synthadoc.core.queue.JobQueue.purge",
               new=AsyncMock(return_value=5)) as mock_purge:
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.delete("/jobs?older_than=3")
    assert resp.status_code == 200
    assert resp.json()["purged"] == 5
    assert resp.json()["older_than_days"] == 3
    mock_purge.assert_awaited_once_with(older_than_days=3)


def test_scaffold_endpoint_enqueues_job(tmp_wiki):
    """POST /jobs/scaffold enqueues a scaffold job and returns its ID."""
    from synthadoc.integration.http_server import create_app
    with patch("synthadoc.core.queue.JobQueue.enqueue",
               new=AsyncMock(return_value="scaf-01")) as mock_enqueue:
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.post("/jobs/scaffold", json={"domain": "Canadian tax law"})
    assert resp.status_code == 200
    assert resp.json()["job_id"] == "scaf-01"
    mock_enqueue.assert_awaited_once_with("scaffold", {"domain": "Canadian tax law"})


def test_scaffold_endpoint_rejects_empty_domain(tmp_wiki):
    """POST /jobs/scaffold with an empty domain returns 422."""
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        resp = client.post("/jobs/scaffold", json={"domain": ""})
    assert resp.status_code == 422


def test_audit_history_endpoint(tmp_wiki):
    """GET /audit/history returns ingest records."""
    from synthadoc.integration.http_server import create_app
    fake_records = [
        {"source_path": "paper.pdf", "wiki_page": "ai-basics",
         "tokens": 500, "cost_usd": 0.001, "ingested_at": "2026-04-17T10:00:00"}
    ]
    with patch("synthadoc.storage.log.AuditDB.list_ingests",
               new=AsyncMock(return_value=fake_records)):
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.get("/audit/history?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["records"][0]["wiki_page"] == "ai-basics"


def test_audit_costs_endpoint(tmp_wiki):
    """GET /audit/costs returns cost summary."""
    from synthadoc.integration.http_server import create_app
    fake_summary = {"total_tokens": 1200, "total_cost_usd": 0.0024, "daily": []}
    with patch("synthadoc.storage.log.AuditDB.cost_summary",
               new=AsyncMock(return_value=fake_summary)):
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.get("/audit/costs?days=7")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_tokens"] == 1200
    assert data["total_cost_usd"] == pytest.approx(0.0024)


def test_query_response_includes_knowledge_gap_fields(tmp_wiki):
    """GET /query must include knowledge_gap and suggested_searches in response."""
    from synthadoc.integration.http_server import create_app
    from synthadoc.agents.query_agent import QueryResult
    with patch("synthadoc.core.orchestrator.Orchestrator.query",
               new=AsyncMock(return_value=QueryResult(
                   question="q", answer="answer", citations=[],
                   knowledge_gap=False, suggested_searches=[],
               ))):
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.get("/query", params={"q": "test question"})
    assert resp.status_code == 200
    data = resp.json()
    assert "knowledge_gap" in data
    assert "suggested_searches" in data


def test_query_response_gap_true_includes_suggestions(tmp_wiki):
    """When knowledge_gap=True, suggested_searches must be a non-empty list."""
    from synthadoc.integration.http_server import create_app
    from synthadoc.agents.query_agent import QueryResult
    with patch("synthadoc.core.orchestrator.Orchestrator.query",
               new=AsyncMock(return_value=QueryResult(
                   question="q", answer="No info found.", citations=[],
                   knowledge_gap=True,
                   suggested_searches=["canadian vegetable spring planting", "frost dates Canada"],
               ))):
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.get("/query", params={"q": "vegetables in Canada?"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["knowledge_gap"] is True
    assert data["suggested_searches"] == ["canadian vegetable spring planting", "frost dates Canada"]


def test_query_post_response_includes_gap_fields(tmp_wiki):
    """POST /query must also include knowledge_gap and suggested_searches."""
    from synthadoc.integration.http_server import create_app
    from synthadoc.agents.query_agent import QueryResult
    with patch("synthadoc.core.orchestrator.Orchestrator.query",
               new=AsyncMock(return_value=QueryResult(
                   question="q", answer="answer", citations=[],
                   knowledge_gap=True, suggested_searches=["search string"],
               ))):
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.post("/query", json={"question": "test"})
    assert resp.status_code == 200
    data = resp.json()
    assert "knowledge_gap" in data
    assert "suggested_searches" in data


def test_job_response_includes_progress_field(tmp_wiki):
    """GET /jobs/{id} must include a progress field (may be null)."""
    from synthadoc.integration.http_server import create_app
    from synthadoc.core.queue import Job, JobStatus
    fake_job = Job(id="job-p1", operation="ingest", payload={"source": "search for: housing"},
                   status=JobStatus.PENDING, retries=0, error=None, progress=None)
    with patch("synthadoc.core.queue.JobQueue.list_jobs",
               new=AsyncMock(return_value=[fake_job])):
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.get("/jobs/job-p1")
    assert resp.status_code == 200
    assert "progress" in resp.json()


def test_list_jobs_includes_progress_field(tmp_wiki):
    """GET /jobs must include progress field on each job."""
    from synthadoc.integration.http_server import create_app
    from synthadoc.core.queue import Job, JobStatus
    fake_job = Job(id="job-p2", operation="ingest", payload={"source": "file.pdf"},
                   status=JobStatus.PENDING, retries=0, error=None, progress=None)
    with patch("synthadoc.core.queue.JobQueue.list_jobs",
               new=AsyncMock(return_value=[fake_job])):
        with TestClient(create_app(wiki_root=tmp_wiki)) as client:
            resp = client.get("/jobs")
    assert resp.status_code == 200
    jobs = resp.json()
    assert len(jobs) >= 1
    for job in jobs:
        assert "progress" in job


def test_analyse_endpoint_returns_structure(tmp_wiki):
    """POST /analyse returns source and analysis keys."""
    from synthadoc.integration.http_server import create_app
    from synthadoc.skills.base import ExtractedContent

    app = create_app(wiki_root=tmp_wiki)
    mock_extracted = ExtractedContent(text="AI is important.", source_path="test.md", metadata={})
    mock_analysis = {"entities": ["AI"], "tags": ["ai"], "summary": "AI summary.", "relevant": True}

    with patch("synthadoc.agents.skill_agent.SkillAgent.extract",
               new=AsyncMock(return_value=mock_extracted)), \
         patch("synthadoc.agents.ingest_agent.IngestAgent._analyse",
               new=AsyncMock(return_value=mock_analysis)), \
         patch("synthadoc.providers.make_provider", return_value=AsyncMock()):
        with TestClient(app) as client:
            resp = client.post("/analyse", json={"source": "test.md"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "test.md"
    assert "analysis" in data
    assert "entities" in data["analysis"]


def test_analyse_endpoint_empty_wiki(tmp_wiki):
    """POST /analyse works when the wiki has no pages."""
    from synthadoc.integration.http_server import create_app
    from synthadoc.skills.base import ExtractedContent

    app = create_app(wiki_root=tmp_wiki)
    mock_extracted = ExtractedContent(text="", source_path="empty.md", metadata={})
    mock_analysis = {"entities": [], "tags": [], "summary": "", "relevant": False}

    with patch("synthadoc.agents.skill_agent.SkillAgent.extract",
               new=AsyncMock(return_value=mock_extracted)), \
         patch("synthadoc.agents.ingest_agent.IngestAgent._analyse",
               new=AsyncMock(return_value=mock_analysis)), \
         patch("synthadoc.providers.make_provider", return_value=AsyncMock()):
        with TestClient(app) as client:
            resp = client.post("/analyse", json={"source": "empty.md"})

    assert resp.status_code == 200
    assert resp.json()["source"] == "empty.md"
