# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import logging

from synthadoc.config import Config, load_config
from synthadoc.core.cache import CacheManager
from synthadoc.core.cost_guard import CostGuard
from synthadoc.core.hooks import HookExecutor
from synthadoc.core.queue import JobQueue
from synthadoc.observability.telemetry import get_tracer, setup_telemetry
from synthadoc.providers import make_provider
from synthadoc.providers.ollama import OllamaProvider
from synthadoc.providers.pricing import estimate_cost
from synthadoc.storage.log import AuditDB, LogWriter
from synthadoc.storage.search import HybridSearch
from synthadoc.storage.wiki import WikiStorage

logger = logging.getLogger(__name__)


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
        self._log_agent_config()

    def _log_agent_config(self) -> None:
        """Log the effective provider/model for each named agent slot at startup."""
        slots = ["default", "ingest", "query", "lint", "skill"]
        parts = []
        seen: dict[str, str] = {}
        for slot in slots:
            cfg = self._cfg.agents.resolve(slot)
            label = f"{cfg.provider}/{cfg.model}"
            raw = getattr(self._cfg.agents, slot, None)
            if slot == "default" or raw is not None:
                parts.append(f"{slot}={label}")
                seen[slot] = label
        logger.info("LLM agents — %s", " | ".join(parts))

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
        # auto_confirm is reserved for when cost gate is wired to the ingest flow (v0.2+).
        # Cost tracking returns $0.0000 in v0.1, so cost_guard.check() is not called here yet.
        from synthadoc.agents.ingest_agent import IngestAgent
        try:
            agent = IngestAgent(
                provider=make_provider("ingest", self._cfg),
                store=self._store, search=self._search,
                log_writer=self._log, audit_db=self._audit,
                cache=self._cache, max_pages=self._cfg.ingest.max_pages_per_ingest,
                cache_version=self._cfg.cache.version,
            )
            result = await agent.ingest(source, force=force, bust_cache=force)
            _agent_cfg = self._cfg.agents.resolve("ingest")
            result.cost_usd = estimate_cost(
                _agent_cfg.model,
                result.input_tokens,
                result.output_tokens,
                is_local=(_agent_cfg.provider == "ollama"),
            )
            # Fan out web search child sources — batch insert in one transaction
            if result.child_sources:
                await self._queue.enqueue_many(
                    "ingest",
                    [{"source": s, "force": False} for s in result.child_sources],
                )

            await self._queue.complete(job_id, result={
                "pages_created": result.pages_created,
                "pages_updated": result.pages_updated,
                "pages_flagged": result.pages_flagged,
                "child_sources_enqueued": len(result.child_sources),
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
            import httpx
            import logging
            from synthadoc.errors import DomainBlockedException
            if isinstance(e, DomainBlockedException):
                await self._auto_block_domain(e)
                await self._queue.skip(job_id, str(e))
            elif isinstance(e, (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.PoolTimeout)):
                # Transient network timeout — retry with backoff, no traceback.
                logging.getLogger(__name__).warning(
                    "URL fetch timed out for job %s (%s) — will retry", job_id, source
                )
                await self._queue.fail(job_id, f"ReadTimeout: {source}")
            elif isinstance(e, httpx.HTTPStatusError):
                status = e.response.status_code
                if 400 <= status < 500:
                    # Permanent client error (404, 410, 451, etc.) — skip, no retry, no traceback.
                    logging.getLogger(__name__).warning(
                        "HTTP %s fetching %s — skipping job %s", status, source, job_id
                    )
                    await self._queue.skip(job_id, f"HTTP {status}: {source}")
                else:
                    # 5xx server error — transient, retry with backoff, no traceback.
                    logging.getLogger(__name__).warning(
                        "HTTP %s fetching %s — will retry job %s", status, source, job_id
                    )
                    await self._queue.fail(job_id, f"HTTP {status}: {source}")
            else:
                await self._queue.fail(job_id, str(e))
                raise

    async def _auto_block_domain(self, exc: "DomainBlockedException") -> None:
        """Persist a newly discovered blocked domain and record an audit event."""
        import json
        import logging
        from datetime import datetime, timezone

        blocked_path = self._root / ".synthadoc" / "blocked_domains.json"
        try:
            existing: list = json.loads(blocked_path.read_text(encoding="utf-8")) \
                if blocked_path.exists() else []
            if exc.domain not in existing:
                existing.append(exc.domain)
                blocked_path.write_text(
                    json.dumps(existing, indent=2), encoding="utf-8"
                )
        except Exception as write_err:
            logging.getLogger(__name__).warning(
                "Could not persist blocked domain %s: %s", exc.domain, write_err
            )

        try:
            await self._audit.record_audit_event(
                job_id="system",
                event="domain_auto_blocked",
                metadata={
                    "domain": exc.domain,
                    "url": exc.url,
                    "status_code": exc.status_code,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception:
            pass

    async def query(self, question: str):
        from synthadoc.agents.query_agent import QueryAgent
        result = await QueryAgent(
            provider=make_provider("query", self._cfg),
            store=self._store, search=self._search,
            gap_score_threshold=self._cfg.query.gap_score_threshold,
        ).query(question)
        _provider = make_provider("query", self._cfg)
        _model = self._cfg.agents.resolve("query").model
        cost_usd = estimate_cost(
            _model,
            result.input_tokens,
            result.output_tokens,
            is_local=isinstance(_provider, OllamaProvider),
        )
        await self._audit.record_query(
            question=question,
            sub_questions_count=len(result.citations) or 1,
            tokens=result.tokens_used,
            cost_usd=cost_usd,
        )
        self._log.log_query(
            question=question,
            sub_questions=len(result.citations) or 1,
            citations=result.citations,
            tokens=result.tokens_used,
            cost_usd=cost_usd,
        )
        return result

    async def lint(self, scope: str = "all", auto_resolve: bool = False) -> str:
        """Enqueue a lint job. The server worker loop executes it."""
        return await self._queue.enqueue("lint", {"scope": scope, "auto_resolve": auto_resolve})

    async def _run_scaffold(self, job_id: str, domain: str) -> None:
        from synthadoc.agents.scaffold_agent import ScaffoldAgent
        try:
            wiki_dir = self._root / "wiki"
            protected_slugs = [p.stem for p in wiki_dir.glob("*.md")]
            result = await ScaffoldAgent(
                provider=make_provider("ingest", self._cfg)
            ).scaffold(domain=domain, protected_slugs=protected_slugs or None)
            (self._root / "wiki" / "index.md").write_text(
                result.index_md, encoding="utf-8", newline="\n")
            (self._root / "AGENTS.md").write_text(
                result.agents_md, encoding="utf-8", newline="\n")
            (self._root / "wiki" / "purpose.md").write_text(
                result.purpose_md, encoding="utf-8", newline="\n")
            await self._queue.complete(job_id, result={
                "domain": domain,
                "categories": len(result.index_md.splitlines()),
            })
        except Exception as e:
            await self._queue.fail(job_id, str(e))
            raise

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
