# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from synthadoc.core.orchestrator import Orchestrator
from synthadoc.config import load_config


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    """Build a minimal HTTPStatusError for testing."""
    request = httpx.Request("GET", "https://example.com/page")
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    return httpx.HTTPStatusError(
        message=f"{status_code}", request=request, response=response
    )


@pytest.mark.asyncio
async def test_orchestrator_init_creates_dbs(tmp_wiki):
    orch = Orchestrator(wiki_root=tmp_wiki, config=load_config())
    await orch.init()
    assert (tmp_wiki / ".synthadoc" / "jobs.db").exists()
    assert (tmp_wiki / ".synthadoc" / "audit.db").exists()
    assert (tmp_wiki / ".synthadoc" / "cache.db").exists()


@pytest.mark.asyncio
async def test_orchestrator_ingest_returns_job_id(tmp_wiki):
    orch = Orchestrator(wiki_root=tmp_wiki, config=load_config())
    await orch.init()
    source = tmp_wiki / "raw_sources" / "test.md"
    source.write_text("# Test\nContent.", encoding="utf-8")
    with patch.object(orch, "_run_ingest", new=AsyncMock()):
        job_id = await orch.ingest(str(source))
    assert job_id


@pytest.mark.asyncio
async def test_run_ingest_http_404_skips_job(tmp_wiki):
    """A 404 response must skip the job immediately with no retry and no exception raised."""
    orch = Orchestrator(wiki_root=tmp_wiki, config=load_config())
    await orch.init()
    job_id = await orch._queue.enqueue("ingest", {"source": "https://example.com/gone", "force": False})

    mock_agent = MagicMock()
    mock_agent.ingest = AsyncMock(side_effect=_http_status_error(404))
    with patch("synthadoc.core.orchestrator.make_provider", return_value=MagicMock()), \
         patch("synthadoc.agents.ingest_agent.IngestAgent", return_value=mock_agent):
        # Must NOT raise — the worker loop must continue cleanly
        await orch._run_ingest(job_id, "https://example.com/gone", auto_confirm=True)

    from synthadoc.core.queue import JobStatus
    jobs = await orch._queue.list_jobs(status=JobStatus.SKIPPED)
    assert any(j.id == job_id for j in jobs)


@pytest.mark.asyncio
async def test_run_ingest_llm_skip_marks_job_skipped(tmp_wiki):
    """When IngestAgent returns result.skipped=True the job must be SKIPPED, not COMPLETED."""
    from synthadoc.agents.ingest_agent import IngestResult

    orch = Orchestrator(wiki_root=tmp_wiki, config=load_config())
    await orch.init()
    job_id = await orch._queue.enqueue("ingest", {"source": "https://example.com/oos", "force": False})

    skipped_result = IngestResult(source="https://example.com/oos", skipped=True, skip_reason="out of scope (purpose.md)")
    mock_agent = MagicMock()
    mock_agent.ingest = AsyncMock(return_value=skipped_result)
    with patch("synthadoc.core.orchestrator.make_provider", return_value=MagicMock()), \
         patch("synthadoc.agents.ingest_agent.IngestAgent", return_value=mock_agent):
        await orch._run_ingest(job_id, "https://example.com/oos", auto_confirm=True)

    from synthadoc.core.queue import JobStatus
    skipped = await orch._queue.list_jobs(status=JobStatus.SKIPPED)
    completed = await orch._queue.list_jobs(status=JobStatus.COMPLETED)
    assert any(j.id == job_id for j in skipped), "LLM-skipped job must have SKIPPED status"
    assert not any(j.id == job_id for j in completed), "LLM-skipped job must not be COMPLETED"


@pytest.mark.asyncio
async def test_run_ingest_http_5xx_retries_job(tmp_wiki):
    """A 5xx response must re-queue the job for retry (PENDING), not skip it."""
    orch = Orchestrator(wiki_root=tmp_wiki, config=load_config())
    await orch.init()
    job_id = await orch._queue.enqueue("ingest", {"source": "https://example.com/flaky", "force": False})

    mock_agent = MagicMock()
    mock_agent.ingest = AsyncMock(side_effect=_http_status_error(503))
    with patch("synthadoc.core.orchestrator.make_provider", return_value=MagicMock()), \
         patch("synthadoc.agents.ingest_agent.IngestAgent", return_value=mock_agent):
        await orch._run_ingest(job_id, "https://example.com/flaky", auto_confirm=True)

    from synthadoc.core.queue import JobStatus
    # fail() with retries remaining → status becomes PENDING again (re-queued for retry)
    pending_jobs = await orch._queue.list_jobs(status=JobStatus.PENDING)
    skipped_jobs = await orch._queue.list_jobs(status=JobStatus.SKIPPED)
    assert any(j.id == job_id for j in pending_jobs), "5xx job should be re-queued for retry"
    assert not any(j.id == job_id for j in skipped_jobs), "5xx job must not be skipped"


@pytest.mark.asyncio
async def test_vector_migration_embeds_existing_pages(tmp_wiki):
    """_run_vector_migration must embed all pages not yet in embeddings.db."""
    from unittest.mock import patch, AsyncMock
    from synthadoc.core.orchestrator import Orchestrator
    from synthadoc.config import Config, AgentsConfig, AgentConfig, SearchConfig
    from synthadoc.storage.search import VectorStore

    wiki_dir = tmp_wiki / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    (wiki_dir / "test-page.md").write_text(
        "---\ntitle: Test\ntags: []\nstatus: active\n"
        "confidence: high\ncreated: '2026-01-01'\nsources: []\n---\nContent here.",
        encoding="utf-8",
    )

    cfg = Config(
        agents=AgentsConfig(default=AgentConfig(provider="gemini", model="gemini-2.0-flash")),
        search=SearchConfig(vector=True),
    )
    orch = Orchestrator(wiki_root=tmp_wiki, config=cfg)
    with patch.dict("sys.modules", {"fastembed": MagicMock()}):
        await orch._search.init_vector()

    with patch.object(orch._search, "_embed_text", return_value=[0.1, 0.2, 0.3, 0.4]):
        await orch._run_vector_migration()

    vs = VectorStore(tmp_wiki / ".synthadoc" / "embeddings.db")
    slugs = await vs.list_slugs()
    assert "test-page" in slugs


@pytest.mark.asyncio
async def test_vector_migration_skips_already_embedded(tmp_wiki):
    """_run_vector_migration must skip pages already in embeddings.db."""
    from unittest.mock import patch
    from synthadoc.core.orchestrator import Orchestrator
    from synthadoc.config import Config, AgentsConfig, AgentConfig, SearchConfig
    from synthadoc.storage.search import VectorStore

    wiki_dir = tmp_wiki / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    (wiki_dir / "existing.md").write_text(
        "---\ntitle: Existing\ntags: []\nstatus: active\n"
        "confidence: high\ncreated: '2026-01-01'\nsources: []\n---\nContent.",
        encoding="utf-8",
    )

    cfg = Config(
        agents=AgentsConfig(default=AgentConfig(provider="gemini", model="gemini-2.0-flash")),
        search=SearchConfig(vector=True),
    )
    orch = Orchestrator(wiki_root=tmp_wiki, config=cfg)
    with patch.dict("sys.modules", {"fastembed": MagicMock()}):
        await orch._search.init_vector()

    # Pre-populate embeddings
    vs = VectorStore(tmp_wiki / ".synthadoc" / "embeddings.db")
    await vs.upsert("existing", [0.9, 0.1, 0.0, 0.0])

    embed_calls = []
    original = orch._search._embed_text
    def fake_embed(text):
        embed_calls.append(text)
        return [0.1, 0.2, 0.3, 0.4]

    with patch.object(orch._search, "_embed_text", side_effect=fake_embed):
        await orch._run_vector_migration()

    # Already embedded — should not be re-embedded
    assert len(embed_calls) == 0


@pytest.mark.asyncio
async def test_run_ingest_domain_blocked_skips_job(tmp_wiki):
    """DomainBlockedException must skip the job without retrying."""
    from synthadoc.errors import DomainBlockedException

    orch = Orchestrator(wiki_root=tmp_wiki, config=load_config())
    await orch.init()
    job_id = await orch._queue.enqueue("ingest", {"source": "https://blocked.com/page", "force": False})

    exc = DomainBlockedException(domain="blocked.com", url="https://blocked.com/page", status_code=403)
    mock_agent = MagicMock()
    mock_agent.ingest = AsyncMock(side_effect=exc)
    with patch("synthadoc.core.orchestrator.make_provider", return_value=MagicMock()), \
         patch("synthadoc.agents.ingest_agent.IngestAgent", return_value=mock_agent):
        await orch._run_ingest(job_id, "https://blocked.com/page", auto_confirm=True)

    from synthadoc.core.queue import JobStatus
    skipped = await orch._queue.list_jobs(status=JobStatus.SKIPPED)
    assert any(j.id == job_id for j in skipped)


@pytest.mark.asyncio
async def test_run_ingest_daily_quota_exhausted_fails_permanent(tmp_wiki):
    """DailyQuotaExhaustedException must permanently fail the job (no retry)."""
    from synthadoc.errors import DailyQuotaExhaustedException

    orch = Orchestrator(wiki_root=tmp_wiki, config=load_config())
    await orch.init()
    job_id = await orch._queue.enqueue("ingest", {"source": "https://example.com", "force": False})

    exc = DailyQuotaExhaustedException(provider="anthropic")
    mock_agent = MagicMock()
    mock_agent.ingest = AsyncMock(side_effect=exc)
    with patch("synthadoc.core.orchestrator.make_provider", return_value=MagicMock()), \
         patch("synthadoc.agents.ingest_agent.IngestAgent", return_value=mock_agent):
        await orch._run_ingest(job_id, "https://example.com", auto_confirm=True)

    from synthadoc.core.queue import JobStatus
    failed = await orch._queue.list_jobs(status=JobStatus.FAILED)
    assert any(j.id == job_id for j in failed)


@pytest.mark.asyncio
async def test_run_ingest_coding_tool_quota_fails_permanent(tmp_wiki):
    """CodingToolQuotaExhaustedException must permanently fail the job."""
    from synthadoc.errors import CodingToolQuotaExhaustedException

    orch = Orchestrator(wiki_root=tmp_wiki, config=load_config())
    await orch.init()
    job_id = await orch._queue.enqueue("ingest", {"source": "https://example.com", "force": False})

    exc = CodingToolQuotaExhaustedException("claude-code")
    mock_agent = MagicMock()
    mock_agent.ingest = AsyncMock(side_effect=exc)
    with patch("synthadoc.core.orchestrator.make_provider", return_value=MagicMock()), \
         patch("synthadoc.agents.ingest_agent.IngestAgent", return_value=mock_agent):
        await orch._run_ingest(job_id, "https://example.com", auto_confirm=True)

    from synthadoc.core.queue import JobStatus
    failed = await orch._queue.list_jobs(status=JobStatus.FAILED)
    assert any(j.id == job_id for j in failed)


@pytest.mark.asyncio
async def test_run_ingest_connect_error_retries_job(tmp_wiki):
    """httpx.ConnectError must re-queue the job for retry (PENDING)."""
    orch = Orchestrator(wiki_root=tmp_wiki, config=load_config())
    await orch.init()
    job_id = await orch._queue.enqueue("ingest", {"source": "https://unreachable.com", "force": False})

    mock_agent = MagicMock()
    mock_agent.ingest = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    with patch("synthadoc.core.orchestrator.make_provider", return_value=MagicMock()), \
         patch("synthadoc.agents.ingest_agent.IngestAgent", return_value=mock_agent):
        await orch._run_ingest(job_id, "https://unreachable.com", auto_confirm=True)

    from synthadoc.core.queue import JobStatus
    pending = await orch._queue.list_jobs(status=JobStatus.PENDING)
    assert any(j.id == job_id for j in pending)


@pytest.mark.asyncio
async def test_run_ingest_environment_error_fails_permanent(tmp_wiki):
    """EnvironmentError (missing provider binary) must permanently fail the job."""
    orch = Orchestrator(wiki_root=tmp_wiki, config=load_config())
    await orch.init()
    job_id = await orch._queue.enqueue("ingest", {"source": "file.pdf", "force": False})

    mock_agent = MagicMock()
    mock_agent.ingest = AsyncMock(side_effect=EnvironmentError("binary not found"))
    with patch("synthadoc.core.orchestrator.make_provider", return_value=MagicMock()), \
         patch("synthadoc.agents.ingest_agent.IngestAgent", return_value=mock_agent):
        await orch._run_ingest(job_id, "file.pdf", auto_confirm=True)

    from synthadoc.core.queue import JobStatus
    failed = await orch._queue.list_jobs(status=JobStatus.FAILED)
    assert any(j.id == job_id for j in failed)


@pytest.mark.asyncio
async def test_resume_returns_job_count(tmp_wiki):
    """resume() must re-queue all pending jobs and return the count."""
    orch = Orchestrator(wiki_root=tmp_wiki, config=load_config())
    await orch.init()
    await orch._queue.enqueue("ingest", {"source": "file1.md", "force": False})
    await orch._queue.enqueue("ingest", {"source": "file2.md", "force": False})

    count = await orch.resume()
    assert count >= 2


@pytest.mark.asyncio
async def test_vector_migration_noop_when_vector_disabled(tmp_wiki):
    """_run_vector_migration must be a no-op when search.vector=False."""
    from unittest.mock import patch
    from synthadoc.core.orchestrator import Orchestrator
    from synthadoc.config import Config, AgentsConfig, AgentConfig, SearchConfig

    wiki_dir = tmp_wiki / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    (wiki_dir / "page.md").write_text(
        "---\ntitle: Page\ntags: []\nstatus: active\n"
        "confidence: high\ncreated: '2026-01-01'\nsources: []\n---\nContent.",
        encoding="utf-8",
    )

    cfg = Config(
        agents=AgentsConfig(default=AgentConfig(provider="gemini", model="gemini-2.0-flash")),
        search=SearchConfig(vector=False),
    )
    orch = Orchestrator(wiki_root=tmp_wiki, config=cfg)

    embed_calls = []
    with patch.object(orch._search, "_embed_text", side_effect=lambda t: embed_calls.append(t) or [0.1]):
        await orch._run_vector_migration()

    assert embed_calls == []
