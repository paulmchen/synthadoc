# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest
from synthadoc.core.queue import JobQueue, JobStatus


@pytest.mark.asyncio
async def test_enqueue_dequeue(tmp_wiki):
    q = JobQueue(tmp_wiki / ".synthadoc" / "jobs.db")
    await q.init()
    job_id = await q.enqueue("ingest", {"source": "paper.pdf"})
    job = await q.dequeue()
    assert job.id == job_id
    assert job.operation == "ingest"
    assert job.status == JobStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_complete_job(tmp_wiki):
    q = JobQueue(tmp_wiki / ".synthadoc" / "jobs.db")
    await q.init()
    job_id = await q.enqueue("ingest", {"source": "x.pdf"})
    job = await q.dequeue()
    await q.complete(job.id)
    jobs = await q.list_jobs(status=JobStatus.COMPLETED)
    assert any(j.id == job_id for j in jobs)


@pytest.mark.asyncio
async def test_fail_retries_then_dies(tmp_wiki):
    q = JobQueue(tmp_wiki / ".synthadoc" / "jobs.db", max_retries=2)
    await q.init()
    await q.enqueue("ingest", {"source": "x.pdf"})
    job = await q.dequeue()
    await q.fail(job.id, "timeout")
    job = await q.dequeue()
    await q.fail(job.id, "timeout")
    dead = await q.list_jobs(status=JobStatus.DEAD)
    assert len(dead) == 1


@pytest.mark.asyncio
async def test_delete_job_atomic(tmp_wiki):
    from synthadoc.storage.log import AuditDB
    q = JobQueue(tmp_wiki / ".synthadoc" / "jobs.db")
    await q.init()
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    job_id = await q.enqueue("ingest", {"source": "x.pdf"})
    job = await q.dequeue()
    await q.complete(job.id)
    await q.delete(job_id, audit_db=audit)
    all_jobs = await q.list_jobs()
    assert not any(j.id == job_id for j in all_jobs)


@pytest.mark.asyncio
async def test_queue_handles_overflow(tmp_wiki):
    q = JobQueue(tmp_wiki / ".synthadoc" / "jobs.db")
    await q.init()
    for i in range(10):
        await q.enqueue("ingest", {"source": f"file{i}.pdf"})
    pending = await q.list_jobs(status=JobStatus.PENDING)
    assert len(pending) == 10


# ── Corner cases ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fail_exactly_at_max_retries_becomes_dead(tmp_wiki):
    """Job must become dead on the Nth failure where N == max_retries."""
    q = JobQueue(tmp_wiki / ".synthadoc" / "jobs.db", max_retries=3)
    await q.init()
    await q.enqueue("ingest", {"source": "x.pdf"})
    for _ in range(3):
        job = await q.dequeue()
        assert job is not None
        await q.fail(job.id, "error")
    dead = await q.list_jobs(status=JobStatus.DEAD)
    assert len(dead) == 1


@pytest.mark.asyncio
async def test_fail_before_max_retries_stays_pending(tmp_wiki):
    """Job must return to PENDING after a failure when retries remain."""
    q = JobQueue(tmp_wiki / ".synthadoc" / "jobs.db", max_retries=3)
    await q.init()
    await q.enqueue("ingest", {"source": "x.pdf"})
    job = await q.dequeue()
    await q.fail(job.id, "transient error")
    pending = await q.list_jobs(status=JobStatus.PENDING)
    assert any(j.id == job.id for j in pending)


@pytest.mark.asyncio
async def test_skip_does_not_retry(tmp_wiki):
    """Skipped jobs must not reappear in the pending queue."""
    q = JobQueue(tmp_wiki / ".synthadoc" / "jobs.db")
    await q.init()
    job_id = await q.enqueue("ingest", {"source": "blocked.com"})
    job = await q.dequeue()
    await q.skip(job.id, "domain blocked")
    pending = await q.list_jobs(status=JobStatus.PENDING)
    assert not any(j.id == job_id for j in pending)
    skipped = await q.list_jobs(status=JobStatus.SKIPPED)
    assert any(j.id == job_id for j in skipped)


@pytest.mark.asyncio
async def test_fail_permanent_goes_to_failed_not_dead(tmp_wiki):
    """fail_permanent must set status=failed, not dead, regardless of retry count."""
    q = JobQueue(tmp_wiki / ".synthadoc" / "jobs.db", max_retries=3)
    await q.init()
    job_id = await q.enqueue("ingest", {"source": "stub.pdf"})
    job = await q.dequeue()
    await q.fail_permanent(job.id, "NotImplementedError: skill stub")
    failed = await q.list_jobs(status=JobStatus.FAILED)
    assert any(j.id == job_id for j in failed)
    dead = await q.list_jobs(status=JobStatus.DEAD)
    assert not any(j.id == job_id for j in dead)


@pytest.mark.asyncio
async def test_dequeue_empty_queue_returns_none(tmp_wiki):
    """Dequeueing from an empty queue must return None, not raise."""
    q = JobQueue(tmp_wiki / ".synthadoc" / "jobs.db")
    await q.init()
    result = await q.dequeue()
    assert result is None


@pytest.mark.asyncio
async def test_dequeue_fifo_order(tmp_wiki):
    """Jobs must be dequeued in the order they were enqueued (FIFO)."""
    q = JobQueue(tmp_wiki / ".synthadoc" / "jobs.db")
    await q.init()
    ids = []
    for i in range(3):
        ids.append(await q.enqueue("ingest", {"source": f"file{i}.pdf"}))
    for expected_id in ids:
        job = await q.dequeue()
        assert job.id == expected_id
        await q.complete(job.id)


@pytest.mark.asyncio
async def test_enqueue_many_all_pending(tmp_wiki):
    """enqueue_many must insert all jobs as PENDING in a single transaction."""
    q = JobQueue(tmp_wiki / ".synthadoc" / "jobs.db")
    await q.init()
    payloads = [{"source": f"https://example.com/page-{i}"} for i in range(20)]
    ids = await q.enqueue_many("ingest", payloads)
    assert len(ids) == 20
    pending = await q.list_jobs(status=JobStatus.PENDING)
    assert len(pending) == 20


@pytest.mark.asyncio
async def test_retry_resets_retries_counter(tmp_wiki):
    """retry() must reset the retries counter to 0 so the job gets a full retry budget."""
    q = JobQueue(tmp_wiki / ".synthadoc" / "jobs.db", max_retries=2)
    await q.init()
    job_id = await q.enqueue("ingest", {"source": "x.pdf"})
    # Exhaust retries → dead
    for _ in range(2):
        job = await q.dequeue()
        await q.fail(job.id, "error")
    dead = await q.list_jobs(status=JobStatus.DEAD)
    assert any(j.id == job_id for j in dead)
    # Manually retry → should reset retries and return to pending
    await q.retry(job_id)
    pending = await q.list_jobs(status=JobStatus.PENDING)
    assert any(j.id == job_id for j in pending)
    job = next(j for j in pending if j.id == job_id)
    assert job.retries == 0


@pytest.mark.asyncio
async def test_purge_removes_old_completed_and_dead(tmp_wiki):
    """purge() must remove completed and dead jobs older than the threshold."""
    import aiosqlite
    q = JobQueue(tmp_wiki / ".synthadoc" / "jobs.db")
    await q.init()
    job_id = await q.enqueue("ingest", {"source": "old.pdf"})
    job = await q.dequeue()
    await q.complete(job.id)
    # Backdate the job so it appears old
    async with aiosqlite.connect(q._path) as db:
        await db.execute(
            "UPDATE jobs SET created_at=datetime('now','-10 days') WHERE id=?", (job_id,)
        )
        await db.commit()
    removed = await q.purge(older_than_days=7)
    assert removed == 1
    all_jobs = await q.list_jobs()
    assert not any(j.id == job_id for j in all_jobs)


@pytest.mark.asyncio
async def test_purge_keeps_recent_jobs(tmp_wiki):
    """purge() must not remove jobs newer than the threshold."""
    q = JobQueue(tmp_wiki / ".synthadoc" / "jobs.db")
    await q.init()
    job_id = await q.enqueue("ingest", {"source": "recent.pdf"})
    job = await q.dequeue()
    await q.complete(job.id)
    removed = await q.purge(older_than_days=7)
    assert removed == 0
    all_jobs = await q.list_jobs()
    assert any(j.id == job_id for j in all_jobs)


@pytest.mark.asyncio
async def test_update_progress_persists(tmp_wiki):
    q = JobQueue(tmp_wiki / ".synthadoc" / "jobs.db")
    await q.init()
    job_id = await q.enqueue("ingest", {"source": "search for: housing"})
    await q.update_progress(job_id, {"phase": "searching"})
    jobs = await q.list_jobs()
    job = next(j for j in jobs if j.id == job_id)
    assert job.progress == {"phase": "searching"}

@pytest.mark.asyncio
async def test_update_progress_overwrites(tmp_wiki):
    q = JobQueue(tmp_wiki / ".synthadoc" / "jobs.db")
    await q.init()
    job_id = await q.enqueue("ingest", {"source": "search for: housing"})
    await q.update_progress(job_id, {"phase": "searching"})
    await q.update_progress(job_id, {"phase": "found_urls", "total": 5})
    jobs = await q.list_jobs()
    job = next(j for j in jobs if j.id == job_id)
    assert job.progress["phase"] == "found_urls"
    assert job.progress["total"] == 5

@pytest.mark.asyncio
async def test_progress_is_none_for_new_jobs(tmp_wiki):
    q = JobQueue(tmp_wiki / ".synthadoc" / "jobs.db")
    await q.init()
    job_id = await q.enqueue("ingest", {"source": "file.pdf"})
    jobs = await q.list_jobs()
    job = next(j for j in jobs if j.id == job_id)
    assert job.progress is None

@pytest.mark.asyncio
async def test_progress_migration_adds_column_to_existing_db(tmp_wiki):
    """Simulates a v0.1.0 DB that lacks the progress column."""
    import aiosqlite
    db_path = tmp_wiki / ".synthadoc" / "jobs.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE jobs (
                id TEXT PRIMARY KEY,
                operation TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                retries INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                result TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.execute(
            "INSERT INTO jobs (id, operation, payload) VALUES ('old1', 'ingest', '{}')"
        )
        await db.commit()
    q = JobQueue(db_path)
    await q.init()
    jobs = await q.list_jobs()
    assert any(j.id == "old1" for j in jobs)
    job = next(j for j in jobs if j.id == "old1")
    assert job.progress is None

@pytest.mark.asyncio
async def test_dequeued_job_has_progress_field(tmp_wiki):
    """Dequeued Job object must expose progress field."""
    q = JobQueue(tmp_wiki / ".synthadoc" / "jobs.db")
    await q.init()
    job_id = await q.enqueue("ingest", {"source": "file.pdf"})
    await q.update_progress(job_id, {"phase": "searching"})
    job = await q.dequeue()
    assert job is not None
    assert job.progress == {"phase": "searching"}


@pytest.mark.asyncio
async def test_init_resets_in_progress_to_pending_on_restart(tmp_wiki):
    """Jobs left in_progress from a crashed session must be reset to pending on init()."""
    import aiosqlite
    db_path = tmp_wiki / ".synthadoc" / "jobs.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE jobs (
                id TEXT PRIMARY KEY,
                operation TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                retries INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                result TEXT,
                progress TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.execute(
            "INSERT INTO jobs (id, operation, payload, status) VALUES ('stuck1', 'ingest', '{}', 'in_progress')"
        )
        await db.commit()
    q = JobQueue(db_path)
    await q.init()
    jobs = await q.list_jobs()
    stuck = next(j for j in jobs if j.id == "stuck1")
    assert stuck.status.value == "pending"


@pytest.mark.asyncio
async def test_requeue_resets_to_pending_without_incrementing_retries(tmp_wiki):
    """requeue() must reset status to pending and leave retry counter unchanged."""
    q = JobQueue(tmp_wiki / ".synthadoc" / "jobs.db")
    await q.init()
    job_id = await q.enqueue("ingest", {"source": "https://example.com"})
    await q.dequeue()
    await q.requeue(job_id, "rate_limit: too many requests")
    jobs = await q.list_jobs()
    job = next(j for j in jobs if j.id == job_id)
    assert job.status.value == "pending"
    assert job.retries == 0


@pytest.mark.asyncio
async def test_requeue_does_not_count_toward_max_retries(tmp_wiki):
    """Multiple requeue() calls must not exhaust the retry budget."""
    q = JobQueue(tmp_wiki / ".synthadoc" / "jobs.db", max_retries=2)
    await q.init()
    job_id = await q.enqueue("ingest", {"source": "https://example.com"})
    for _ in range(5):
        await q.dequeue()
        await q.requeue(job_id, "rate_limit")
    jobs = await q.list_jobs()
    job = next(j for j in jobs if j.id == job_id)
    assert job.status.value == "pending"
    assert job.retries == 0


@pytest.mark.asyncio
async def test_cancel_pending_marks_all_pending_as_cancelled(tmp_wiki):
    """cancel_pending() must mark all pending jobs as cancelled and return the count."""
    q = JobQueue(tmp_wiki / ".synthadoc" / "jobs.db")
    await q.init()
    ids = [await q.enqueue("ingest", {"source": f"url{i}.com"}) for i in range(4)]
    # Complete one so it should not be cancelled
    job = await q.dequeue()
    await q.complete(job.id)
    count = await q.cancel_pending()
    assert count == 3
    jobs = {j.id: j for j in await q.list_jobs()}
    for jid in ids:
        if jid == job.id:
            assert jobs[jid].status.value == "completed"
        else:
            assert jobs[jid].status.value == "cancelled"


@pytest.mark.asyncio
async def test_cancel_pending_returns_zero_when_nothing_pending(tmp_wiki):
    """cancel_pending() on an empty queue must return 0 without error."""
    q = JobQueue(tmp_wiki / ".synthadoc" / "jobs.db")
    await q.init()
    count = await q.cancel_pending()
    assert count == 0
