# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations
import asyncio, json, uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional
import aiosqlite


class JobStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD = "dead"
    SKIPPED = "skipped"       # deliberately not retried (e.g. domain auto-blocked)
    CANCELLED = "cancelled"   # pending job cancelled by user


@dataclass
class Job:
    id: str
    operation: str
    payload: dict
    status: JobStatus
    retries: int
    error: Optional[str]
    created_at: Optional[str] = None
    result: Optional[dict] = None
    progress: Optional[dict] = None


class JobQueue:
    def __init__(self, db_path: Path, max_retries: int = 3) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._max_retries = max_retries
        self._lock = asyncio.Lock()

    async def init(self) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    operation TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    retries INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    result TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )""")
            # Migrate existing DBs that predate the result column
            try:
                await db.execute("ALTER TABLE jobs ADD COLUMN result TEXT")
            except Exception:
                pass  # column already exists
            # Migrate existing DBs that predate the progress column
            try:
                await db.execute("ALTER TABLE jobs ADD COLUMN progress TEXT")
            except Exception:
                pass  # column already exists
            # Reset any jobs left in_progress from a previous crashed session
            await db.execute("UPDATE jobs SET status='pending' WHERE status='in_progress'")
            await db.commit()

    async def enqueue(self, operation: str, payload: dict) -> str:
        job_id = str(uuid.uuid4())[:8]
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT INTO jobs (id,operation,payload,status) VALUES (?,?,?,'pending')",
                (job_id, operation, json.dumps(payload)),
            )
            await db.commit()
        return job_id

    async def enqueue_many(self, operation: str, payloads: list[dict]) -> list[str]:
        """Enqueue multiple jobs in a single connection and transaction."""
        job_ids = [str(uuid.uuid4())[:8] for _ in payloads]
        async with aiosqlite.connect(self._path) as db:
            await db.executemany(
                "INSERT INTO jobs (id,operation,payload,status) VALUES (?,?,?,'pending')",
                [(jid, operation, json.dumps(p)) for jid, p in zip(job_ids, payloads)],
            )
            await db.commit()
        return job_ids

    async def dequeue(self) -> Optional[Job]:
        async with self._lock:
            async with aiosqlite.connect(self._path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT * FROM jobs WHERE status='pending' ORDER BY created_at LIMIT 1"
                ) as cur:
                    row = await cur.fetchone()
                if not row:
                    return None
                await db.execute("UPDATE jobs SET status='in_progress' WHERE id=?", (row["id"],))
                await db.commit()
                return Job(id=row["id"], operation=row["operation"],
                           payload=json.loads(row["payload"]),
                           status=JobStatus.IN_PROGRESS,
                           retries=row["retries"], error=row["error"],
                           created_at=row["created_at"],
                           result=json.loads(row["result"]) if row["result"] else None,
                           progress=json.loads(row["progress"]) if row["progress"] else None)

    async def complete(self, job_id: str, result: Optional[dict] = None) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "UPDATE jobs SET status='completed', result=? WHERE id=?",
                (json.dumps(result) if result else None, job_id),
            )
            await db.commit()

    async def update_progress(self, job_id: str, data: dict) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "UPDATE jobs SET progress=? WHERE id=?",
                (json.dumps(data), job_id),
            )
            await db.commit()

    async def fail(self, job_id: str, error: str) -> None:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT retries FROM jobs WHERE id=?", (job_id,)) as cur:
                row = await cur.fetchone()
            retries = (row["retries"] + 1) if row else 1
            new_status = "dead" if retries >= self._max_retries else "pending"
            await db.execute(
                "UPDATE jobs SET status=?,retries=?,error=? WHERE id=?",
                (new_status, retries, error, job_id),
            )
            await db.commit()

    async def requeue(self, job_id: str, error: str = "") -> None:
        """Reset a job to pending without incrementing the retry counter.

        Used for transient infrastructure errors (rate limits, server overload)
        that should not count against the job's retry budget.
        """
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "UPDATE jobs SET status='pending', error=? WHERE id=?",
                (error or None, job_id),
            )
            await db.commit()

    async def fail_permanent(self, job_id: str, error: str) -> None:
        """Fail a job immediately with no retry — for non-transient errors."""
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "UPDATE jobs SET status='failed',error=? WHERE id=?",
                (error, job_id),
            )
            await db.commit()

    async def skip(self, job_id: str, reason: str) -> None:
        """Mark a job as skipped — deliberately not retried (e.g. domain auto-blocked)."""
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "UPDATE jobs SET status='skipped',error=? WHERE id=?",
                (reason, job_id),
            )
            await db.commit()

    async def delete(self, job_id: str, audit_db=None) -> None:
        if audit_db:
            await audit_db.record_audit_event(job_id, "job_deleted", {"deleted_by": "user"})
        async with aiosqlite.connect(self._path) as db:
            await db.execute("DELETE FROM jobs WHERE id=?", (job_id,))
            await db.commit()

    async def retry(self, job_id: str) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "UPDATE jobs SET status='pending',retries=0,error=NULL WHERE id=?", (job_id,)
            )
            await db.commit()

    async def cancel_pending(self) -> int:
        """Mark all pending jobs as cancelled. Returns the number of jobs cancelled."""
        async with aiosqlite.connect(self._path) as db:
            async with db.execute("SELECT COUNT(*) FROM jobs WHERE status='pending'") as cur:
                count = (await cur.fetchone())[0]
            await db.execute(
                "UPDATE jobs SET status='cancelled', error='cancelled by user' WHERE status='pending'"
            )
            await db.commit()
        return count

    async def purge(self, older_than_days: int) -> int:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM jobs WHERE status IN ('completed','dead') "
                "AND created_at < datetime('now', ?)",
                (f"-{older_than_days} days",)
            ) as cur:
                count = (await cur.fetchone())[0]
            await db.execute(
                "DELETE FROM jobs WHERE status IN ('completed','dead') "
                "AND created_at < datetime('now', ?)",
                (f"-{older_than_days} days",)
            )
            await db.commit()
        return count

    async def list_jobs(self, status: Optional[JobStatus] = None) -> list[Job]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            q = ("SELECT * FROM jobs WHERE status=? ORDER BY created_at"
                 if status else "SELECT * FROM jobs ORDER BY created_at")
            args = (status.value,) if status else ()
            async with db.execute(q, args) as cur:
                rows = await cur.fetchall()
            return [Job(id=r["id"], operation=r["operation"],
                        payload=json.loads(r["payload"]),
                        status=JobStatus(r["status"]),
                        retries=r["retries"], error=r["error"],
                        created_at=r["created_at"],
                        result=json.loads(r["result"]) if r["result"] else None,
                        progress=json.loads(r["progress"]) if r["progress"] else None,
                        ) for r in rows]
