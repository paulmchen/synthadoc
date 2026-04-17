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


class LintRequest(BaseModel):
    scope: str = "all"
    auto_resolve: bool = False


class AnalyseRequest(BaseModel):
    source: str

    @field_validator("source")
    @classmethod
    def source_not_empty(cls, v):
        if not v.strip():
            raise ValueError("source must not be empty")
        return v


async def _worker_loop(orch) -> None:
    """Background task: poll jobs.db and execute pending jobs."""
    from synthadoc.core.queue import JobStatus
    while True:
        try:
            job = await orch.queue.dequeue()
            if job:
                if job.operation == "ingest":
                    source = job.payload.get("source", "")
                    force = job.payload.get("force", False)
                    await orch._run_ingest(job.id, source, auto_confirm=True, force=force)
                elif job.operation == "lint":
                    scope = job.payload.get("scope", "all")
                    auto_resolve = job.payload.get("auto_resolve", False)
                    await orch._run_lint(job.id, scope=scope, auto_resolve=auto_resolve)
        except Exception:
            logger.exception("Worker loop error — job recorded in jobs.db; continuing")

        await asyncio.sleep(_WORKER_POLL_SECONDS)


def create_app(wiki_root: Path, max_body_bytes: int = _MAX_BODY_BYTES) -> FastAPI:
    import os
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

    app = FastAPI(title="synthadoc", version="0.1.0", lifespan=lifespan)
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

    @app.get("/query")
    async def query(q: str):
        if not q.strip():
            raise HTTPException(status_code=400, detail="q must not be empty")
        result = await app.state.orch.query(q)
        return {"answer": result.answer, "citations": result.citations}

    @app.post("/query")
    async def query_post(req: QueryRequest):
        result = await app.state.orch.query(req.question)
        return {"answer": result.answer, "citations": result.citations}

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
        source = req.source
        # Leave URLs and web-search prefixes untouched — only resolve file paths.
        if not source.startswith(("http://", "https://", "search for:")):
            p = _Path(source)
            if not p.is_absolute():
                # Resolve relative paths against the wiki root so that vault-relative
                # paths sent by the Obsidian plugin (e.g. "raw_sources/file.pdf") work
                # regardless of the server's working directory.
                source = str((wiki_root / source).resolve())
        job_id = await app.state.orch.queue.enqueue(
            "ingest", {"source": source, "force": req.force}
        )
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
        _SKIP = {"index", "log", "dashboard", "purpose"}
        wiki_dir = wiki_root / "wiki"
        pages = list(wiki_dir.glob("*.md"))

        page_texts: dict[str, str] = {p.stem: p.read_text(encoding="utf-8") for p in pages}

        contradicted = [
            stem for stem, text in page_texts.items()
            if stem not in _SKIP and "status: contradicted" in text
        ]

        referenced: set[str] = set()
        for text in page_texts.values():
            for link in _WIKILINK_RE.findall(text):
                slug_part = link.split("|")[0].strip()
                referenced.add(slug_part.lower().replace(" ", "-"))

        orphan_slugs = [
            stem for stem in page_texts
            if stem not in referenced and stem not in _SKIP
        ]

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
                 "error": j.error, "result": j.result} for j in jobs]

    @app.get("/jobs/{job_id}")
    async def get_job(job_id: str):
        jobs = await app.state.orch.queue.list_jobs()
        for j in jobs:
            if j.id == job_id:
                return {"id": j.id, "status": j.status, "operation": j.operation,
                        "created_at": str(j.created_at), "error": j.error,
                        "result": j.result}
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")

    @app.delete("/jobs/{job_id}")
    async def delete_job(job_id: str):
        await app.state.orch.queue.delete(job_id, app.state.orch._audit)
        return {"deleted": job_id}

    return app
