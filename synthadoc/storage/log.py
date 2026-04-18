# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiosqlite


class LogWriter:
    def __init__(self, log_path: Path) -> None:
        self._path = Path(log_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.write_text("# Activity Log\n\n", encoding="utf-8", newline="\n")

    def _append(self, text: str) -> None:
        with open(self._path, "a", encoding="utf-8", newline="\n") as f:
            f.write(text + "\n")

    def log_ingest(self, source: str, pages_created: list, pages_updated: list,
                   pages_flagged: list, tokens: int, cost_usd: float, cache_hits: int) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        self._append(
            f"\n## {ts} | INGEST | {source}\n"
            f"- Created: {pages_created or 'none'}\n"
            f"- Updated: {pages_updated or 'none'}\n"
            f"- Flagged: {pages_flagged or 'none'}\n"
            f"- Tokens: {tokens:,} | Cost: ${cost_usd:.4f} | Cache hits: {cache_hits}\n"
        )

    def log_lint(self, resolved: int, flagged: int, orphans: int) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        self._append(
            f"\n## {ts} | LINT\n"
            f"- Resolved: {resolved} | Flagged: {flagged} | Orphans: {orphans}\n"
        )

    def log_query(self, question: str, sub_questions: int,
                  citations: list, tokens: int, cost_usd: float) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        self._append(
            f"\n## {ts} | QUERY\n"
            f"- Question: {question[:120]}\n"
            f"- Sub-questions: {sub_questions} | Citations: {citations or 'none'}\n"
            f"- Tokens: {tokens:,} | Cost: ${cost_usd:.4f}\n"
        )


class AuditDB:
    def __init__(self, db_path: Path) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    async def init(self) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ingests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_hash TEXT NOT NULL,
                    source_size INTEGER NOT NULL,
                    source_path TEXT NOT NULL,
                    wiki_page TEXT NOT NULL,
                    tokens INTEGER,
                    cost_usd REAL,
                    ingested_at TEXT NOT NULL
                )""")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT,
                    event TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    metadata TEXT
                )""")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS queries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question TEXT NOT NULL,
                    sub_questions_count INTEGER NOT NULL DEFAULT 1,
                    tokens INTEGER,
                    cost_usd REAL,
                    queried_at TEXT NOT NULL
                )""")
            await db.commit()

    async def record_ingest(self, source_hash: str, source_size: int,
                            source_path: str, wiki_page: str,
                            tokens: int, cost_usd: float) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT INTO ingests (source_hash,source_size,source_path,wiki_page,"
                "tokens,cost_usd,ingested_at) VALUES (?,?,?,?,?,?,?)",
                (source_hash, source_size, source_path, wiki_page, tokens, cost_usd, ts),
            )
            await db.commit()

    async def find_by_hash_only(self, source_hash: str) -> Optional[dict]:
        """Return the first ingest record matching source_hash, or None.

        The returned dict uses key ``size`` (mapped from ``source_size``) so
        callers can compare ``existing["size"]`` against the current file size.
        """
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM ingests WHERE source_hash=? LIMIT 1",
                (source_hash,),
            ) as cur:
                row = await cur.fetchone()
            if row is None:
                return None
            d = dict(row)
            # Expose "size" alias so callers can do existing["size"]
            d.setdefault("size", d.get("source_size"))
            return d

    async def find_by_hash(self, source_hash: str, source_size: int) -> Optional[dict]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM ingests WHERE source_hash=? AND source_size=? LIMIT 1",
                (source_hash, source_size),
            ) as cur:
                row = await cur.fetchone()
            return dict(row) if row else None

    async def list_ingests(self, limit: int = 50) -> list[dict]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT source_path, wiki_page, tokens, cost_usd, ingested_at "
                "FROM ingests ORDER BY id ASC LIMIT ?",
                (limit,),
            ) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def list_events(self, limit: int = 100) -> list[dict]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT job_id, event, timestamp, metadata "
                "FROM audit_events ORDER BY id ASC LIMIT ?",
                (limit,),
            ) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def record_query(self, question: str, sub_questions_count: int,
                           tokens: int, cost_usd: float) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT INTO queries (question,sub_questions_count,tokens,cost_usd,queried_at)"
                " VALUES (?,?,?,?,?)",
                (question, sub_questions_count, tokens, cost_usd, ts),
            )
            await db.commit()

    async def list_queries(self, limit: int = 50) -> list[dict]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT question, sub_questions_count, tokens, cost_usd, queried_at"
                " FROM queries ORDER BY id DESC LIMIT ?",
                (limit,),
            ) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def cost_summary(self, days: int = 30) -> dict:
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT day, SUM(day_tokens) as day_tokens, SUM(day_cost) as day_cost FROM (
                    SELECT DATE(ingested_at) as day, tokens as day_tokens, cost_usd as day_cost
                    FROM ingests WHERE ingested_at >= ?
                    UNION ALL
                    SELECT DATE(queried_at) as day, tokens as day_tokens, cost_usd as day_cost
                    FROM queries WHERE queried_at >= ?
                ) GROUP BY day ORDER BY day DESC
            """, (cutoff, cutoff)) as cur:
                rows = await cur.fetchall()

        total_tokens = 0
        total_cost = 0.0
        daily = []
        for r in rows:
            rd = dict(r)
            total_tokens += rd.get("day_tokens") or 0
            total_cost += rd.get("day_cost") or 0.0
            daily.append({"day": rd["day"], "cost_usd": rd.get("day_cost") or 0.0})

        return {"total_tokens": total_tokens, "total_cost_usd": total_cost, "daily": daily}

    async def record_audit_event(self, job_id: str, event: str, metadata: dict) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT INTO audit_events (job_id,event,timestamp,metadata) VALUES (?,?,?,?)",
                (job_id, event, ts, json.dumps(metadata)),
            )
            await db.commit()
