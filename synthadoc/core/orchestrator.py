# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from synthadoc.config import Config, load_config
from synthadoc.core.cache import CacheManager
from synthadoc.core.cost_guard import CostGuard
from synthadoc.core.hooks import HookExecutor
from synthadoc.core.queue import JobQueue
from synthadoc.observability.telemetry import get_tracer, setup_telemetry
from synthadoc.providers import make_provider
from synthadoc.storage.log import AuditDB, LogWriter
from synthadoc.storage.search import HybridSearch
from synthadoc.storage.wiki import WikiStorage


class Orchestrator:
    def __init__(self, wiki_root: Path, config: Optional[Config] = None) -> None:
        self._root = wiki_root
        self._cfg = config or load_config(
            project_config=wiki_root / ".synthadoc" / "config.toml")
        sd = wiki_root / ".synthadoc"
        sd.mkdir(parents=True, exist_ok=True)
        (sd / "logs").mkdir(exist_ok=True)

        self._queue  = JobQueue(sd / "jobs.db", max_retries=self._cfg.queue.max_retries)
        self.queue   = self._queue
        self._audit  = AuditDB(sd / "audit.db")
        self._cache  = CacheManager(sd / "cache.db")
        self._store  = WikiStorage(wiki_root / "wiki")
        self._search = HybridSearch(self._store, sd / "embeddings.db")
        self._log    = LogWriter(wiki_root / "log.md")
        self._cost   = CostGuard(self._cfg.cost)
        self._hooks  = HookExecutor(self._cfg.hooks)
        setup_telemetry(sd / "logs" / "traces.jsonl")

    async def init(self) -> None:
        await self._queue.init()
        await self._audit.init()
        await self._cache.init()

    async def ingest(self, source: str, force: bool = False) -> str:
        """Enqueue an ingest job. The server worker loop executes it."""
        return await self._queue.enqueue("ingest", {"source": source, "force": force})

    async def resume(self) -> int:
        """Re-enqueue all pending and failed jobs."""
        from synthadoc.core.queue import JobStatus
        jobs = await self._queue.list_jobs(status=JobStatus.PENDING)
        jobs += await self._queue.list_jobs(status=JobStatus.FAILED)
        for job in jobs:
            await self._queue.retry(job.id)
        return len(jobs)

    async def _run_ingest(self, job_id: str, source: str, auto_confirm: bool,
                          force: bool = False) -> None:
        from synthadoc.agents.ingest_agent import IngestAgent
        try:
            agent = IngestAgent(
                provider=make_provider("ingest", self._cfg),
                store=self._store, search=self._search,
                log_writer=self._log, audit_db=self._audit,
                cache=self._cache, max_pages=self._cfg.ingest.max_pages_per_ingest,
            )
            result = await agent.ingest(source, force=force, bust_cache=force)
            await self._queue.complete(job_id, result={
                "pages_created": result.pages_created,
                "pages_updated": result.pages_updated,
                "pages_flagged": result.pages_flagged,
                "tokens_used": result.tokens_used,
                "cost_usd": result.cost_usd,
            })
            self._hooks.fire("on_ingest_complete", {
                "event": "on_ingest_complete", "wiki": str(self._root),
                "source": source,
                "pages_created": result.pages_created,
                "pages_updated": result.pages_updated,
                "pages_flagged": result.pages_flagged,
                "tokens_used": result.tokens_used,
                "cost_usd": result.cost_usd,
            })
        except NotImplementedError as e:
            # Skill is a known stub — fail immediately, no retry
            await self._queue.fail_permanent(job_id, str(e))
        except Exception as e:
            await self._queue.fail(job_id, str(e))
            raise

    async def query(self, question: str):
        from synthadoc.agents.query_agent import QueryAgent
        return await QueryAgent(
            provider=make_provider("query", self._cfg),
            store=self._store, search=self._search, cache=self._cache,
        ).query(question)

    async def lint(self, scope: str = "all", auto_resolve: bool = False) -> str:
        """Enqueue a lint job. The server worker loop executes it."""
        return await self._queue.enqueue("lint", {"scope": scope, "auto_resolve": auto_resolve})

    async def _run_lint(self, job_id: str, scope: str = "all", auto_resolve: bool = False) -> None:
        from synthadoc.agents.lint_agent import LintAgent
        try:
            report = await LintAgent(
                provider=make_provider("lint", self._cfg),
                store=self._store, log_writer=self._log,
                confidence_threshold=self._cfg.cost.auto_resolve_confidence_threshold,
            ).lint(scope=scope, auto_resolve=auto_resolve)
            await self._queue.complete(job_id)
            self._hooks.fire("on_lint_complete", {
                "event": "on_lint_complete", "wiki": str(self._root),
                "contradictions_found": report.contradictions_found,
                "orphans": report.orphan_slugs,
            })
        except Exception as e:
            await self._queue.fail(job_id, str(e))
            raise
