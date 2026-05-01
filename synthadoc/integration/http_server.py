# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, field_validator
from starlette.middleware.base import BaseHTTPMiddleware

import logging
import re

logger = logging.getLogger(__name__)

_MAX_BODY_BYTES = 10 * 1024 * 1024  # 10 MB


def _classify_llm_error(exc: Exception) -> "HTTPException | None":
    """Return a meaningful HTTPException for known LLM API error codes, or None."""
    from synthadoc.errors import DailyQuotaExhaustedException
    _SWITCH = "Switch to another provider by editing [agents] in .synthadoc/config.toml and restarting the server (options: anthropic, openai, gemini, groq, minimax, deepseek, ollama)."
    if isinstance(exc, DailyQuotaExhaustedException):
        return HTTPException(
            status_code=503,
            detail=f"Daily quota exhausted for {exc.provider} — no requests possible until midnight UTC. {_SWITCH}",
        )

    # openai/anthropic SDKs set status_code directly on the exception;
    # httpx.HTTPStatusError (used by OllamaProvider) stores it on exc.response.
    code = getattr(exc, "status_code", None)
    if code is None:
        resp = getattr(exc, "response", None)
        code = getattr(resp, "status_code", None)

    if code == 401:
        msg = str(exc)
        if "deepseek" in msg.lower() or "api.deepseek.com" in msg.lower():
            var = "DEEPSEEK_API_KEY"
        elif "minimax" in msg.lower():
            var = "MINIMAX_API_KEY"
        elif "groq" in msg.lower():
            var = "GROQ_API_KEY"
        elif "generativelanguage" in msg.lower() or "gemini" in msg.lower():
            var = "GEMINI_API_KEY"
        elif "anthropic" in msg.lower():
            var = "ANTHROPIC_API_KEY"
        elif "openai" in msg.lower():
            var = "OPENAI_API_KEY"
        else:
            var = "your provider's API key env var"
        return HTTPException(
            status_code=401,
            detail=f"LLM provider rejected the API key (401). Check that {var} is set correctly and restart the server.",
        )
    if code == 402:
        body = getattr(exc, "body", None) or {}
        err_msg = ""
        if isinstance(body, dict):
            err_msg = body.get("error", {}).get("message", "")
        detail = err_msg or "Insufficient balance"
        return HTTPException(
            status_code=402,
            detail=f"LLM provider payment required (402): {detail}. Top up your account balance at your provider's billing page and retry.",
        )
    if code == 429:
        msg = str(exc)
        _SWITCH_429 = "Switch to another provider by editing [agents] in .synthadoc/config.toml and restarting the server (options: anthropic, openai, gemini, groq, minimax, deepseek, ollama)."
        if "generativelanguage.googleapis.com" in msg or "gemini" in msg.lower():
            hint = f"Gemini free-tier quota exhausted. Wait for the daily reset or switch providers. {_SWITCH_429}"
        elif "groq" in msg.lower():
            hint = f"Groq rate limit hit. Wait for the retry window or switch providers. {_SWITCH_429}"
        elif "anthropic" in msg.lower():
            hint = f"Anthropic rate limit hit. Wait a moment or switch providers. {_SWITCH_429}"
        elif "openai" in msg.lower():
            hint = f"OpenAI rate limit hit. Wait a moment or switch providers. {_SWITCH_429}"
        else:
            hint = f"LLM provider rate limit hit. Wait a moment or switch providers. {_SWITCH_429}"
        return HTTPException(
            status_code=429,
            detail=f"LLM quota exceeded (429). {hint}",
        )
    if code == 529:
        return HTTPException(
            status_code=503,
            detail="LLM provider temporarily overloaded (529). Retry in a moment.",
        )
    return None
_WORKER_POLL_SECONDS = 2
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_FM_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


class ContentSizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose Content-Length exceeds the configured limit."""

    def __init__(self, app, max_bytes: int = _MAX_BODY_BYTES) -> None:
        super().__init__(app)
        self._max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length is not None:
            if int(content_length) > self._max_bytes:
                return Response(content="Request body too large", status_code=413)
        return await call_next(request)


class QueryRequest(BaseModel):
    question: str
    save: bool = False

    @field_validator("question")
    @classmethod
    def question_not_empty(cls, v):
        if not v.strip():
            raise ValueError("question must not be empty")
        return v


class IngestRequest(BaseModel):
    source: str
    force: bool = False
    max_results: int | None = None


class LintRequest(BaseModel):
    scope: str = "all"
    auto_resolve: bool = False


class ScaffoldRequest(BaseModel):
    domain: str

    @field_validator("domain")
    @classmethod
    def domain_not_empty(cls, v):
        if not v.strip():
            raise ValueError("domain must not be empty")
        return v


class AnalyseRequest(BaseModel):
    source: str

    @field_validator("source")
    @classmethod
    def source_not_empty(cls, v):
        if not v.strip():
            raise ValueError("source must not be empty")
        return v


def _parse_retry_after(exc: Exception, default: float = 60.0) -> float:
    """Parse 'Please try again in Xm Y.Zs' from a rate-limit error message."""
    m = re.search(r"Please try again in (?:(\d+)m\s*)?(\d+(?:\.\d+)?)s", str(exc))
    if m:
        return float(m.group(1) or 0) * 60 + float(m.group(2))
    return default


async def _worker_loop(orch) -> None:
    """Background task: poll jobs.db and execute pending jobs."""
    sleep_secs = _WORKER_POLL_SECONDS
    while True:
        try:
            job = await orch.queue.dequeue()
            sleep_secs = _WORKER_POLL_SECONDS  # reset after a successful dequeue
            if job:
                if job.operation == "ingest":
                    source = job.payload.get("source", "")
                    force = job.payload.get("force", False)
                    max_results = job.payload.get("max_results")
                    await orch._run_ingest(job.id, source, auto_confirm=True, force=force,
                                           max_results=max_results)
                elif job.operation == "lint":
                    scope = job.payload.get("scope", "all")
                    auto_resolve = job.payload.get("auto_resolve", False)
                    await orch._run_lint(job.id, scope=scope, auto_resolve=auto_resolve)
                elif job.operation == "scaffold":
                    domain = job.payload.get("domain", "")
                    await orch._run_scaffold(job.id, domain=domain)
        except Exception as exc:
            known = _classify_llm_error(exc)
            if known and known.status_code == 503 and "Daily quota" in (known.detail or ""):
                # Daily quota is exhausted for the rest of the day — no point
                # sleeping and retrying. The orchestrator already permanently
                # failed the job; just continue polling without a sleep penalty.
                logger.error("Daily quota exhausted — jobs will fail until midnight UTC. %s",
                             known.detail)
                sleep_secs = _WORKER_POLL_SECONDS
            elif known and known.status_code == 429:
                sleep_secs = _parse_retry_after(exc)
                logger.warning(
                    "Rate limit hit in worker — pausing %.0f s before next job. "
                    "(%d pending jobs will wait.) %s",
                    sleep_secs,
                    len([j for j in asyncio.all_tasks() if not j.done()]),
                    known.detail,
                )
            else:
                logger.exception("Worker loop error — job recorded in jobs.db; continuing")
                sleep_secs = _WORKER_POLL_SECONDS

        await asyncio.sleep(sleep_secs)


def create_app(wiki_root: Path, max_body_bytes: int = _MAX_BODY_BYTES) -> FastAPI:
    import os
    import synthadoc
    from synthadoc.config import load_config
    from synthadoc.core.orchestrator import Orchestrator

    # Expose wiki root so skills (e.g. web_search) can load the dynamic blocked-domains list
    os.environ["SYNTHADOC_WIKI_ROOT"] = str(wiki_root)

    cfg = load_config(project_config=wiki_root / ".synthadoc" / "config.toml")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        orch = Orchestrator(wiki_root=wiki_root, config=cfg)
        await orch.init()
        app.state.orch = orch
        worker = asyncio.create_task(_worker_loop(orch))
        yield
        worker.cancel()

    app = FastAPI(title="synthadoc", version=synthadoc.__version__, lifespan=lifespan)
    app.add_middleware(ContentSizeLimitMiddleware, max_bytes=max_body_bytes)

    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["app://obsidian.md", "http://localhost", "http://127.0.0.1"],
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )

    @app.get("/", response_class=Response)
    async def index():
        from synthadoc.cli.logo import banner_text
        import synthadoc
        text = banner_text(version=synthadoc.__version__)
        text += (
            f"  Endpoints\n"
            f"  ---------------------------------\n"
            f"  GET  /health          liveness probe\n"
            f"  GET  /status          wiki stats\n"
            f"  POST /analyse         analyse source without writing pages\n"
            f"  POST /jobs/ingest     enqueue ingest job\n"
            f"  POST /jobs/lint       enqueue lint job\n"
            f"  GET  /jobs            list jobs\n"
            f"  GET  /jobs/{{id}}       job detail\n"
            f"  POST /query           query the wiki\n"
            f"  GET  /lint/report     orphans + contradictions\n"
        )
        return Response(content=text, media_type="text/plain; charset=utf-8")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/status")
    async def status():
        orch = app.state.orch
        jobs = await orch.queue.list_jobs()
        pending = sum(1 for j in jobs if j.status == "pending")
        return {
            "wiki": str(wiki_root),
            "pages": len(orch._store.list_pages()),
            "jobs_pending": pending,
            "jobs_total": len(jobs),
        }

    async def _run_query(question: str) -> dict:
        try:
            result = await app.state.orch.query(question)
        except Exception as exc:
            known = _classify_llm_error(exc)
            if known:
                logger.warning("LLM rate limit during query: %s", exc)
                raise known from exc
            if isinstance(exc, (EnvironmentError, OSError)) and "[ERR-PROV-" in str(exc):
                logger.warning("Provider not available: %s", exc)
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            logger.exception("Query failed")
            raise HTTPException(status_code=502, detail="LLM provider unavailable") from exc
        return {
            "answer": result.answer,
            "citations": result.citations,
            "knowledge_gap": result.knowledge_gap,
            "suggested_searches": result.suggested_searches,
        }

    @app.get("/query")
    async def query(q: str):
        if not q.strip():
            raise HTTPException(status_code=400, detail="q must not be empty")
        return await _run_query(q)

    @app.post("/query")
    async def query_post(req: QueryRequest):
        return await _run_query(req.question)

    @app.post("/analyse")
    async def analyse_source(req: AnalyseRequest):
        """Run analysis pass on a source and return structured result without writing pages."""
        from synthadoc.agents.ingest_agent import IngestAgent
        from synthadoc.providers import make_provider
        from synthadoc.agents.skill_agent import SkillAgent
        orch = app.state.orch
        agent = IngestAgent(
            provider=make_provider("ingest", orch._cfg),
            store=orch._store, search=orch._search,
            log_writer=orch._log, audit_db=orch._audit,
            cache=orch._cache, max_pages=orch._cfg.ingest.max_pages_per_ingest,
            wiki_root=orch._root,
            cache_version=orch._cfg.cache.version,
            fetch_timeout=orch._cfg.ingest.fetch_timeout_seconds,
        )
        skill = SkillAgent()
        extracted = await skill.extract(req.source)
        text = extracted.text[:8000]
        analysis = await agent._analyse(text, bust_cache=False)
        analysis.pop("_tokens", None)
        return {"source": req.source, "analysis": analysis}

    @app.post("/jobs/ingest")
    async def enqueue_ingest(req: IngestRequest):
        from pathlib import Path as _Path
        from synthadoc.agents.skill_agent import SkillAgent
        source = req.source
        # Normalise backslash URLs so Windows-pasted forms (e.g. "https:\example.com\path")
        # are stored as proper URLs and are not mistakenly path-resolved.
        from synthadoc.agents.skill_agent import _normalize_url
        _normalised = _normalize_url(source)
        if _normalised.lower().startswith(("http://", "https://")):
            source = _normalised
        if SkillAgent().needs_path_resolution(source):
            p = _Path(source)
            if not p.is_absolute():
                # Resolve vault-relative paths (e.g. "raw_sources/file.pdf") against
                # wiki root so they work regardless of server working directory.
                source = str((wiki_root / source).resolve())
        payload: dict = {"source": source, "force": req.force}
        if req.max_results is not None:
            payload["max_results"] = req.max_results
        job_id = await app.state.orch.queue.enqueue("ingest", payload)
        return {"job_id": job_id}

    @app.post("/jobs/lint")
    async def enqueue_lint(req: LintRequest):
        job_id = await app.state.orch.queue.enqueue(
            "lint", {"scope": req.scope, "auto_resolve": req.auto_resolve}
        )
        return {"job_id": job_id}

    @app.get("/lint/report")
    async def lint_report():
        import yaml as _yaml
        from synthadoc.agents.lint_agent import find_orphan_slugs, LINT_SKIP_SLUGS
        wiki_dir = wiki_root / "wiki"
        pages = list(wiki_dir.glob("*.md"))

        page_texts: dict[str, str] = {p.stem: p.read_text(encoding="utf-8") for p in pages}

        contradicted = [
            stem for stem, text in page_texts.items()
            if stem not in LINT_SKIP_SLUGS and "status: contradicted" in text
        ]

        orphan_slugs = find_orphan_slugs(page_texts)

        orphan_details = []
        for slug in orphan_slugs:
            fm_m = _FM_RE.match(page_texts.get(slug, ""))
            fm: dict = {}
            if fm_m:
                try:
                    fm = _yaml.safe_load(fm_m.group(1)) or {}
                except Exception:
                    pass
            title = fm.get("title") or slug.replace("-", " ").title()
            tags = fm.get("tags") or []
            if isinstance(tags, list) and tags:
                hint = ", ".join(str(t) for t in tags[:4])
            else:
                hint = title
            orphan_details.append({
                "slug": slug,
                "index_suggestion": f"- [[{slug}]] — {hint}",
            })

        return {
            "contradictions": contradicted,
            "orphans": [d["slug"] for d in orphan_details],
            "orphan_details": orphan_details,
        }

    @app.get("/jobs")
    async def list_jobs(status: str | None = None):
        from synthadoc.core.queue import JobStatus
        try:
            job_status = JobStatus(status) if status else None
        except ValueError:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail=f"Invalid status {status!r}. Valid values: {[s.value for s in JobStatus]}")
        jobs = await app.state.orch.queue.list_jobs(status=job_status)
        return [{"id": j.id, "status": j.status, "operation": j.operation,
                 "created_at": str(j.created_at), "payload": j.payload,
                 "error": j.error, "result": j.result, "progress": j.progress} for j in jobs]

    @app.get("/jobs/{job_id}")
    async def get_job(job_id: str):
        # O(n) scan — acceptable for typical queue sizes (< 1000 active jobs); add an index if needed
        jobs = await app.state.orch.queue.list_jobs()
        for j in jobs:
            if j.id == job_id:
                return {"id": j.id, "status": j.status, "operation": j.operation,
                        "created_at": str(j.created_at), "error": j.error,
                        "result": j.result, "progress": j.progress}
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")

    @app.delete("/jobs/{job_id}")
    async def delete_job(job_id: str):
        await app.state.orch.queue.delete(job_id, app.state.orch._audit)
        return {"deleted": job_id}

    @app.post("/jobs/{job_id}/retry")
    async def retry_job(job_id: str):
        jobs = await app.state.orch.queue.list_jobs()
        if not any(j.id == job_id for j in jobs):
            raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
        await app.state.orch.queue.retry(job_id)
        return {"retried": job_id}

    @app.post("/jobs/cancel-pending")
    async def cancel_pending_jobs():
        count = await app.state.orch.queue.cancel_pending()
        return {"cancelled": count}

    @app.delete("/jobs")
    async def purge_jobs(older_than: int = 7):
        count = await app.state.orch.queue.purge(older_than_days=older_than)
        return {"purged": count, "older_than_days": older_than}

    @app.post("/jobs/scaffold")
    async def enqueue_scaffold(req: ScaffoldRequest):
        job_id = await app.state.orch.queue.enqueue(
            "scaffold", {"domain": req.domain}
        )
        return {"job_id": job_id}

    @app.get("/audit/history")
    async def audit_history(limit: int = 50):
        records = await app.state.orch._audit.list_ingests(limit=limit)
        return {"records": records, "count": len(records)}

    @app.get("/audit/costs")
    async def audit_costs(days: int = 30):
        return await app.state.orch._audit.cost_summary(days=days)

    @app.get("/audit/queries")
    async def audit_queries(limit: int = 50):
        records = await app.state.orch._audit.list_queries(limit=limit)
        return {"records": records, "count": len(records)}

    @app.get("/audit/events")
    async def audit_events(limit: int = 100):
        records = await app.state.orch._audit.list_events(limit=limit)
        return {"records": records, "count": len(records)}

    return app
