# Synthadoc — Design Document

**Version:** 0.2.0 (released 2026-04-25)  
**Audience:** Product users who want to understand how the system works; developers adding features, skills, and plugins.

**Document owners:** Paul Chen, William Johnason

---

## Table of Contents

1. [Overview](#1-overview)
2. [Core Concepts](#2-core-concepts)
3. [System Architecture](#3-system-architecture)
4. [Agents](#4-agents)
5. [Skills System](#5-skills-system)
6. [Storage](#6-storage)
7. [HTTP API](#7-http-api)
8. [Obsidian Plugin](#8-obsidian-plugin)
9. [CLI](#9-cli)
10. [Configuration](#10-configuration)
11. [Hook System](#11-hook-system)
12. [Cache System](#12-cache-system)
13. [Cost Guard](#13-cost-guard)
14. [Job Queue](#14-job-queue)
15. [Observability and Logging](#15-observability-and-logging)
16. [Security](#16-security)
17. [Plugin Development Guide](#17-plugin-development-guide)
**Appendices**
- [Appendix A — Release Feature Index](#appendix-a--release-feature-index)

---

## 1. Overview

Synthadoc is a **domain-agnostic LLM knowledge compilation engine**. It reads raw source documents and uses an LLM to synthesize them into a persistent structured wiki. Knowledge is compiled at **ingest time** — not at query time. The compiled wiki lives as plain Markdown files that are readable and editable without any tool running.

**Key design principles:**

- **Ingest-time compilation** — synthesis, cross-referencing, and contradiction detection happen once per source, not on every query.
- **Local-first** — all data stays on disk; the server binds only to `127.0.0.1`.
- **Obsidian-native** — wiki pages are valid Obsidian notes with `[[wikilinks]]`, YAML frontmatter, and Dataview compatibility.
- **Layered access** — CLI, HTTP REST API, and MCP server expose the same operations; the agent and storage logic is shared.
- **Extensible by design** — skills (file formats) and providers (LLM backends) are loaded as plugins; no core changes needed to add either.

---

## 2. Core Concepts

### Wiki

A self-contained knowledge base rooted at a filesystem directory. Contains:

```
my-wiki/
  wiki/               ← compiled Markdown pages
  raw_sources/        ← original source documents
  hooks/              ← wiki-specific hook scripts
  AGENTS.md           ← LLM instructions for this domain
  log.md              ← human-readable activity log
  .synthadoc/
    config.toml       ← per-project configuration
    audit.db          ← immutable audit trail
    jobs.db           ← job queue
    cache.db          ← LLM response cache
    embeddings.db     ← BM25 + vector search index
    logs/
      synthadoc.log   ← rotating JSON-lines operational log
      traces.jsonl    ← OpenTelemetry traces
```

### Wiki Page

A Markdown file in `wiki/` with YAML frontmatter:

```yaml
---
title: Alan Turing
tags: [computer-science, cryptography, turing-test]
status: active          # active | contradicted | archived
confidence: high        # high | medium | low
created: '2026-04-10'
sources:
  - file: turing-biography.pdf
    hash: sha256:abc123…
    size: 204800
    ingested: '2026-04-10'
---

# Alan Turing

Content with [[wikilinks]] to related pages…
```

**`status` values:**

| Value | Meaning |
|-------|---------|
| `active` | Normal; up to date |
| `contradicted` | A new source conflicts with this page; needs resolution |
| `archived` | Source removed; page retained for reference |

### Job

Every ingest, lint, and scheduled operation runs as a job:

```
pending → in_progress → completed
                      → failed      (retryable; will retry with backoff)
                      → dead        (max_retries exceeded; requires manual intervention)
                      → skipped     (deliberately not retried; e.g. auto-blocked domain)
```

Jobs persist across server restarts. A dead job can be reset to `pending` with `synthadoc jobs retry <id>`.

### Slug

The filename without extension, derived from the page title. ASCII-safe and CJK-aware:

- Lowercase, hyphens for separators
- Unicode accents decomposed (NFKD)
- CJK characters (Chinese, Japanese, Korean) preserved as-is
- Slug blacklist blocks reserved words (`wiki`, `obsidian`, `index`, `dashboard`, `wikilinks`)
- Collisions resolved by appending `-2`, `-3`, etc.

---

## 3. System Architecture

### Component Map

![Synthadoc Architecture](png/architecture.png)

### Request lifecycle (ingest via CLI)

1. `synthadoc ingest report.pdf -w my-wiki`
2. CLI posts `POST /jobs/ingest {source: "report.pdf"}` to `localhost:7070`
3. HTTP server validates path, writes job to `jobs.db` with status `pending`, returns `{job_id}`
4. Background worker picks up job within 2 seconds
5. Orchestrator instantiates IngestAgent, checks CostGuard
6. SkillAgent detects `.pdf`, lazy-loads `PdfSkill`, extracts text
7. IngestAgent Step 1 — Analysis: `_analyse()` extracts entities, tags, and a 3-sentence summary (cached under key `analyse-v1`)
8. IngestAgent Step 2 — Decision: LLM reads the summary (not raw text) + BM25-retrieved candidate pages + `purpose.md` scope, decides per-page action (`create` / `update` / `skip` / `flag_contradiction`)
9. IngestAgent Step 3 — Write: applies actions; updates frontmatter; writes `[[wikilinks]]`; fires hooks
10. IngestAgent Step 4 — Overview: if any pages were created or updated, regenerates `wiki/overview.md`
11. Job transitions to `completed`; `log.md` updated; `audit.db` record written

---

## 4. Agents

All agents are async Python classes. They receive a job context, write results to storage, and return a summary. Agents never call each other directly — they are dispatched by the Orchestrator.

### IngestAgent

Five-pass pipeline:

| Pass | Model | Purpose |
|------|-------|---------|
| 0 — Vision (optional) | Default | Extract text from image sources (`is_image=True`); requires a vision-capable provider |
| 1 — Analysis (`_analyse()`) | Default | Extract entities, tags, and a 3-sentence summary from raw text. Result cached under key `analyse-v1` keyed by SHA-256 of the text. |
| 2 — Candidate search | None (BM25) | Find existing wiki pages related to extracted entities |
| 3 — Decision | Default | LLM reads summary (not full text) + BM25 candidates + `purpose.md` scope. Outputs per-page action: `create`, `update`, `flag`, `skip` |
| 4 — Write | None | Apply actions; update frontmatter; write `[[wikilinks]]`; fire hooks |
| 5 — Overview | Default | Regenerate `wiki/overview.md` if any pages were created or updated |

**Analysis caching:** The analysis step is expensive (full text read + LLM call). Results are cached in `cache.db` by text SHA-256. Subsequent ingests of the same source (e.g. after a `--force` that hits the decision cache miss) re-use the analysis result without a new LLM call.

**purpose.md scope filtering:** IngestAgent reads `wiki/purpose.md` at init. Its content is prepended to the decision prompt. The LLM can respond with `action="skip"` when the source is clearly outside the wiki's stated scope. If `purpose.md` is absent, all sources are accepted.

**overview.md auto-maintenance:** After any ingest that creates or updates pages, IngestAgent calls `_update_overview()`, which reads the 10 most-recently-modified wiki pages and asks the LLM to write a 2-paragraph overview of the entire wiki. The result is saved to `wiki/overview.md` with `status: auto` frontmatter. This page is excluded from contradiction detection and orphan checks.

**Web search fan-out:** When a source is routed to the `web_search` skill, `ExtractedContent.metadata["child_sources"]` contains the top result URLs. IngestAgent detects this and returns early with the URL list; the Orchestrator enqueues each URL as a separate ingest job. This keeps the web search skill stateless and the queue the single source of work.

**Deduplication:** Every source tracked by SHA-256 in `audit.db`. Hash match → skip. Use `--force` to bypass.

**Slug derivation:**

```python
def _slugify(title: str) -> str:
    normalized = unicodedata.normalize("NFKD", title)
    slug = re.sub(
        r"[^a-z0-9\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]+",
        "-", normalized.lower(),
    ).strip("-")
    return slug or "page-" + hashlib.md5(title.encode()).hexdigest()[:8]
```

**Contradiction flagging:** When Pass 3 returns `flag_contradiction`, the page's frontmatter is updated to `status: contradicted`, both the old claim and new conflicting claim are preserved with `⚠` markers and citations.

**CJK support:** Entity extraction falls back to CJK 2–6 char sequence regex when SpaCy is unavailable. `_slugify` preserves CJK characters. BM25 tokenizer handles CJK unigrams.

### QueryAgent

#### Query Decomposition

**Pipeline:**

```
Question
 → Call 1: decompose() — LLM splits question into 1–N sub-questions (cap=4)
   └─ on any LLM error: fall back to [question]          graceful degradation
 → parallel BM25 search per sub-question                 asyncio.gather()
 → merge candidates — best score wins per slug           deduplication
 → Call 2: LLM synthesises answer from merged context    unchanged from v0.1
 → record_query() in audit.db                            cost + history tracking
 → log_query() in activity log                           operator visibility
```

**Decomposition behaviour:**
- Simple questions decompose to a single sub-question — identical behaviour to v0.1
- Compound questions (e.g. "Who invented FORTRAN and what was the Bombe machine?") decompose into one sub-question per part — each part retrieved independently, pages merged before synthesis
- Comparative questions (e.g. "Compare Turing's contributions with Von Neumann's") retrieve both subjects in parallel
- The LLM returns a JSON array of strings. Markdown code fences (` ```json ``` `) are stripped before parsing — required for cross-model robustness (some providers wrap JSON in fences despite instructions)
- On any failure during decomposition (network error, invalid JSON, empty list, non-array response), the agent falls back silently to `[question]` — the query always completes

**Logging (INFO level):**
```
query is simple — no decomposition (1 sub-question)
query decomposed into 2 sub-question(s): "Who invented FORTRAN?" | "What was the Bombe machine?"
```

**BM25 corpus cache:** `HybridSearch` builds the BM25 corpus once per server session and caches it in memory (`_cached_corpus`). The cache is invalidated by `invalidate_index()` after every `write_page()` call in IngestAgent, so queries always see current wiki content without redundant disk reads.

#### Knowledge Gap Workflow

After the BM25 merge step, a knowledge gap is detected when ANY of three independent signals fire (gap is skipped when `gap_score_threshold = 0`):

1. `len(candidates) < 3` — wiki has almost nothing on the topic
2. `max_score < gap_score_threshold` (default: `2.0`, configurable via `[query] gap_score_threshold` in `synthadoc.toml`) — low keyword overlap
3. Fewer than 2 candidates contain any key noun from the question with sufficient frequency — corpus-relative BM25 scores can be inflated by shared vocabulary; this content-overlap check catches off-topic matches

When a gap fires:

1. `SearchDecomposeAgent.decompose(question)` is called to generate 1–4 focused keyword search strings
2. `QueryResult.knowledge_gap = True` and `QueryResult.suggested_searches = [...]` are set
3. The CLI appends a `[!tip] Knowledge Gap Detected` Obsidian callout with:
   - Obsidian Command Palette path (primary)
   - `synthadoc ingest "search for: ..."` terminal commands (with `-w`)
4. The API response includes `knowledge_gap` and `suggested_searches` fields
5. The Obsidian `QueryModal` renders the same callout using `MarkdownRenderer.render()`

When no gap is detected, `suggested_searches` is `[]` and no callout is shown.

---

### Web Search Decomposition (v0.2.0)

> **Note:** Implementation is in `docs/plans/web-search-decomposition-v0.2.md`. This section describes the delivered behavior.

**Motivation:** The v0.1 web search feature (`synthadoc ingest "search for: <topic>"`) fired a single Tavily API call for the entire input phrase. Decomposing the search intent into multiple focused keyword queries before fetching produces richer, more targeted pages — each sub-query targets a different aspect of the topic.

**Pipeline:**

```
User input: "search for: yard gardening in Canadian climate zones"
 → IngestAgent detects web_search skill
 → strip intent prefix → "yard gardening in Canadian climate zones"
 → SearchDecomposeAgent.decompose() — LLM returns terse keyword strings
   e.g. ["Canada hardiness zones map",
         "planting guide by province Canada",
         "frost dates Canadian cities"]
 → asyncio.gather() — N parallel Tavily API calls
 → deduplicate URLs across results (first-seen wins, order preserved)
 → merged child_sources → existing fan-out unchanged
```

**Key design decisions:**
- Uses a **separate prompt** from `QueryAgent.decompose()` — query decomposition asks "what distinct *questions* does this ask?" (natural-language sub-questions) while search decomposition asks "what distinct *search strings* would find the best authoritative sources?" (terse keyword phrases). The outputs are fundamentally different — they must not share a prompt.
- Implemented as `SearchDecomposeAgent` in `synthadoc/agents/search_decompose_agent.py` — kept separate to avoid coupling the two decomposition strategies.
- Cap: 4 search strings maximum — prevents runaway Tavily API spend.
- Fallback: if LLM call fails, JSON is invalid, or all entries are whitespace, use the original phrase as a single search query — the ingest always completes.

**Logging (INFO level):**
```
web search is simple — no decomposition (1 query)
web search decomposed into 3 queries: "Canada hardiness zones map" | "frost dates Canadian cities" | "planting guide by province Canada"
```

### Semantic Re-ranking

> **Opt-in.** BM25 is the default and works without any additional dependencies.

**Installation:**

```bash
pip install fastembed
```

**Enable in config:**

```toml
[search]
vector = true
vector_top_candidates = 20   # BM25 candidate pool; top_n returned after re-ranking
```

**Embedding model:** `BAAI/bge-small-en-v1.5` (~130 MB), managed by `fastembed`. Downloaded once on the first server start with `vector = true`; cached at `~/.cache/fastembed/` thereafter.

**On first enable**, the server prints and logs:

```
Vector search enabled — downloading embedding model BAAI/bge-small-en-v1.5 (~130 MB)
to ~/.cache/fastembed/. This is a one-time download.
```

**Search flow (when `vector = true`):**

1. BM25 retrieves top `vector_top_candidates` (default 20) candidates
2. The query is embedded; cosine similarity is computed against each candidate's stored vector
3. Results are re-ranked by vector score; top `top_n` (default 8) are returned to the caller

**Migration:** On first enable, a background task embeds all existing wiki pages into `embeddings.db`. BM25 continues to serve all queries during migration — no downtime. Progress is logged every 50 pages. New pages are embedded immediately on write.

**Fallback:** If `embeddings.db` is empty, the model is unavailable, or `fastembed` is not installed, BM25 ranking is used automatically with no error.

**Performance notes:**
- First enable on a large wiki may take several minutes to embed all pages. Subsequent server starts are instant (model and embeddings already cached).
- The re-ranking step is CPU-only and adds single-digit milliseconds per query after migration.
- Set `vector = false` to revert to BM25-only at any time. Existing embeddings are not deleted.

---

### LintAgent

Runs against the entire wiki or a scoped subset:

| Check | What it finds |
|-------|---------------|
| Contradiction | Pages with `status: contradicted` |
| Orphan | Pages with zero inbound `[[wikilinks]]` |
| Stale | Pages whose `sources[]` entries no longer exist on disk |
| Missing link | Entity mentioned in page body but no wikilink created |

**Auto-resolution:** For contradictions, LintAgent asks the LLM to propose a resolution with a confidence score. If score ≥ `auto_resolve_confidence_threshold` (default 0.85), applies automatically. Below threshold, queues for human review.

**Index suggestion:** For orphan pages, LintAgent reads the page frontmatter and generates a ready-to-paste `wiki/index.md` entry: `- [[slug]] — tag1, tag2, tag3`.

**Orphan frontmatter sync:** After computing orphans, both `LintAgent.lint()` (server-side, via `POST /jobs/lint`) and `synthadoc lint report` (CLI, offline) write `orphan: true` or `orphan: false` to each eligible page's YAML frontmatter. This keeps the Obsidian Dataview query (`WHERE orphan = true`) in sync with the computed orphan state without requiring the server to be running after `lint report`.

**Auto-generated page exclusions:** The pages `index`, `dashboard`, `overview`, `log`, and `purpose` are excluded from both orphan detection and contradiction checking. Links from these pages do not count as real inbound references — a page linked only from `overview.md` is still reported as an orphan. These pages are also never flagged as contradicted by the ingest pipeline.

### SkillAgent

Dispatches to the correct skill based on file extension, URL prefix, or intent keyword match. Manages 3-tier lazy loading. Returns `ExtractedContent` to IngestAgent.

When a source is a URL or an intent phrase (e.g. `search for: Dennis Ritchie`), IngestAgent skips the local file checks — there is no file to verify or hash. File-existence validation and SHA-256 dedup only apply to local file paths.

---

## 5. Skills System

Skills extract text from source documents. They are Python classes that subclass `BaseSkill` (`synthadoc/skills/base.py`, Apache-2.0).

### Folder-based skill structure

Each skill is a self-contained directory:

```
pdf/
  SKILL.md          ← YAML frontmatter (parsed by engine) + Markdown body (for humans/LLMs)
  scripts/
    main.py         ← BaseSkill subclass; entry point declared in SKILL.md
  assets/           ← data files bundled with the skill (optional)
  references/       ← reference documents loaded via get_resource() (optional)
```

**`SKILL.md` frontmatter schema:**

```yaml
name: pdf
version: "1.0"
description: Extract text from PDF documents
entry:
  script: scripts/main.py
  class: PdfSkill
triggers:
  extensions: [".pdf"]
  intents: ["pdf", "research paper", "document"]
requires: [pypdf, pdfminer.six]
```

The Markdown body is for human readers and LLMs — never engine-parsed. Use it to document usage, edge cases, and references.

### 3-Tier Lazy Loading

| Tier | What loads | When |
|------|-----------|------|
| 1 — Metadata | `SkillMeta` parsed from `SKILL.md` frontmatter | Always; startup |
| 2 — Body | Full skill class via `importlib.util` | When a matching source is encountered |
| 3 — Resources | Files from `assets/` or `references/` via `get_resource()` | On first access within the skill |

This means importing 20 skills costs essentially zero memory until they are needed.

### Registry cache

`SkillAgent` writes `skill_registry.json` to `<wiki-root>/.synthadoc/` on init. Each entry stores the `SKILL.md` mtime; on subsequent startups, unchanged entries are deserialised without re-parsing YAML (warm start). New, changed, or deleted skill folders are detected automatically.

### Intent-based dispatch

`detect_skill(source)` matches against `triggers.extensions` (file suffix or URL prefix) **and** `triggers.intents` (substring match on lowercased source string). This enables purely intent-driven skills with no file extension — e.g., `web_search` triggers on `"search for"`, `"look up"`, `"find on the web"`, etc.

### Built-in Skills

| Skill | Extensions | Intent phrases | Notes |
|-------|-----------|---------------|-------|
| `pdf` | `.pdf` | `pdf`, `research paper`, `document` | pypdf primary; pdfminer.six fallback if yield < 50 chars/page |
| `url` | `http://`, `https://` | `fetch url`, `web page`, `website` | httpx fetch + BeautifulSoup clean |
| `markdown` | `.md`, `.txt` | `markdown`, `text file`, `notes` | Direct read |
| `docx` | `.docx` | `word document`, `docx` | python-docx |
| `pptx` | `.pptx` | `powerpoint`, `presentation`, `pptx` | python-pptx; each slide rendered as a titled section; speaker notes appended when present |
| `xlsx` | `.xlsx`, `.csv` | `spreadsheet`, `excel`, `csv` | openpyxl |
| `image` | `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.tiff` | `image`, `screenshot`, `diagram`, `photo` | Base64 + vision LLM |
| `web_search` | _(none)_ | `search for`, `find on the web`, `look up`, `web search`, `browse` | Calls Tavily API; returns top result URLs as child sources enqueued individually. Requires `TAVILY_API_KEY`. |

### Custom Skill Locations

Skills are discovered from five locations in priority order:

| Source | Path | Override priority |
|--------|------|------------------|
| `extra_dirs` (programmatic) | Passed at `SkillAgent()` init | Highest |
| Local wiki | `<wiki-root>/skills/` | High |
| Global user | `~/.synthadoc/skills/` | Medium |
| pip entry points | `entry_points('synthadoc.skills')` | Low |
| Built-in | Ships with package (`synthadoc/skills/`) | Lowest |

No server restart needed — registry cache detects changes automatically on next startup.

### BaseSkill Interface

```python
# synthadoc/skills/base.py  (Apache-2.0)
@dataclass
class Triggers:
    extensions: list[str]   # e.g. [".pdf"] or ["http://", "https://"]
    intents:    list[str]   # e.g. ["search for", "look up"]

@dataclass
class SkillMeta:
    name: str
    description: str
    version: str
    entry_script: str       # relative path within skill_dir
    entry_class: str        # class name in that script
    triggers: Triggers
    requires: list[str]     # pip distribution names
    skill_dir: Path = None  # set by SkillAgent after loading

@dataclass
class ExtractedContent:
    text: str
    source_path: str
    metadata: dict = field(default_factory=dict)

class BaseSkill(ABC):

    @abstractmethod
    async def extract(self, source: str) -> ExtractedContent: ...

    def get_resource(self, filename: str) -> str:
        """Load a file from assets/ or references/ within the skill folder."""
        ...
```

---

## 6. Storage

### wiki/ — Page files

Plain Markdown. One file per page. Filename = slug + `.md`. Frontmatter is YAML between `---` delimiters. Body uses standard Markdown with `[[wikilinks]]` for internal references.

### audit.db — Immutable audit trail

SQLite. Two key tables:

**`ingest_log`**

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `source` | TEXT | Original path or URL |
| `hash` | TEXT | `sha256:<hex>` |
| `size` | INTEGER | Bytes |
| `cost_usd` | REAL | |
| `tokens` | INTEGER | |
| `pages_created` | TEXT | JSON array of slugs |
| `pages_updated` | TEXT | JSON array of slugs |
| `ingested_at` | TEXT | UTC ISO-8601 |

**`audit_events`**

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `event` | TEXT | e.g. `contradiction_found`, `auto_resolved`, `cost_gate_triggered` |
| `details` | TEXT | JSON |
| `recorded_at` | TEXT | UTC ISO-8601 |

**`queries`** _(added in v0.2.0)_

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `question` | TEXT | Original question text |
| `sub_questions_count` | INTEGER | Number of sub-questions decomposed (1 for simple questions) |
| `tokens` | INTEGER | Answer call token usage |
| `cost_usd` | REAL | Approximate cost (answer tokens × rate) |
| `queried_at` | TEXT | UTC ISO-8601 |

### jobs.db — Job queue

See [Section 14 — Job Queue](#14-job-queue).

### cache.db — LLM response cache

See [Section 12 — Cache System](#12-cache-system).

### embeddings.db — Search index

BM25 + optional vector index over all wiki pages. When vector search is disabled (default), only the BM25 index is used. When `[search] vector = true`, the same SQLite file also stores a `embeddings` table holding `float32` embedding vectors alongside the BM25 entries.

**BM25 tokenizer** handles ASCII and CJK:

```python
@staticmethod
def _tokenize(text: str) -> list[str]:
    ascii_tokens = re.findall(r"[a-z0-9]+", text.lower())
    cjk_tokens   = re.findall(
        r"[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]", text
    )
    return ascii_tokens + cjk_tokens
```

Note: BM25 IDF requires a minimum of 3 documents in the corpus for non-zero scores when a term appears in exactly one document (formula: `log((N-df+0.5)/(df+0.5))`; N=2, df=1 → log(1) = 0).

---

## 7. HTTP API

**Base URL:** `http://127.0.0.1:<port>` (default port: 7070)

### Middleware

- **CORS:** Allows `app://obsidian.md`, `http://localhost:*`, `http://127.0.0.1:*`
- **ContentSizeLimitMiddleware:** Rejects bodies > 10 MB with HTTP 413
- **Asyncio semaphore:** Max 20 concurrent requests
- **Timeout:** 60 seconds per request

### Endpoints

| Method | Path | Request | Response |
|--------|------|---------|----------|
| `POST` | `/jobs/ingest` | `{source: str}` | `{job_id: str}` |
| `POST` | `/jobs/lint` | `{scope?: str}` | `{job_id: str}` |
| `GET` | `/jobs` | `?status=<filter>` | `[Job]` |
| `GET` | `/jobs/{id}` | — | `Job` |
| `DELETE` | `/jobs/{id}` | — | `{deleted: job_id}` |
| `GET` | `/query` | `?q=<question>` | `{answer: str, citations: [str]}` |
| `POST` | `/query` | `{question: str, save?: bool}` | `{answer: str, citations: [str], slug?: str}` |
| `GET` | `/status` | — | `WikiStatus` |
| `GET` | `/lint/report` | — | `LintReport` |
| `GET` | `/health` | — | `{status: "ok"}` |

**Job object:**

```json
{
  "id": "abc123",
  "status": "completed",
  "operation": "ingest",
  "created_at": "2026-04-10T14:32:01Z",
  "payload": {"source": "report.pdf"},
  "result": {"pages_created": ["alan-turing"], "cost_usd": 0.0, "child_job_ids": []},
  "progress": {"phase": "found_urls", "total": 5},
  "error": null
}
```

The `progress` field is updated in real time during execution (e.g. `{"phase": "searching"}` before Tavily call, `{"phase": "found_urls", "total": N}` after URLs are returned). It is `null` for jobs that do not emit progress. Web search jobs additionally store `child_job_ids` in `result` so callers can track the fan-out URL ingest jobs.

**LintReport object:**

```json
{
  "contradictions": ["grace-hopper"],
  "orphans": ["quantum-computing"],
  "orphan_details": [
    {
      "slug": "quantum-computing",
      "index_suggestion": "- [[quantum-computing]] — physics, computing, qubits"
    }
  ]
}
```

**Note on timestamps:** All `created_at` values are stored and returned as UTC. The Obsidian plugin appends `+00:00` before passing to `new Date()` to ensure correct local-time display.

### Path resolution

`POST /jobs/ingest` accepts:
- Absolute path: `/home/user/docs/report.pdf`
- Vault-relative path: `raw_sources/report.pdf` (resolved against `wiki_root`)
- URL: `https://example.com/article`

### Background worker

The HTTP server runs a background task that polls `jobs.db` every 2 seconds and dispatches pending jobs. Max 4 concurrent ingest jobs (configurable via `max_parallel_ingest`).

---

## 8. Obsidian Plugin

**Package:** `synthadoc-obsidian` (TypeScript)  
**Location:** `obsidian-plugin/` in the repo  
**Version:** 0.2.0

Each vault configures its server URL in plugin settings (default `http://127.0.0.1:7070`).

**Installation:** Build with `npm run build` in `obsidian-plugin/`, then copy `main.js` and
`manifest.json` to `<vault>/.obsidian/plugins/synthadoc/`. Enable in Settings → Community Plugins.
Reload the plugin (toggle off/on) after copying — a full Obsidian restart is not required.

### Command palette

| Command | Behaviour |
|---------|-----------|
| `Synthadoc: Ingest current file as source` | Queues the active file. When no file is active, opens a fuzzy-search file picker (SuggestModal) scoped to `raw_sources/` |
| `Synthadoc: Ingest all sources` | Queues every supported file under the configured raw sources folder |
| `Synthadoc: Ingest from URL...` | Modal with URL input; queues a web URL for ingest |
| `Synthadoc: Query wiki...` | Responsive modal (min 520px, 60vw, max 860px); markdown-rendered answer with citation footer; stays open when clicking elsewhere — must be closed explicitly via ✕ or Escape |
| `Synthadoc: Lint report` | Modal showing contradicted pages and orphans with remediation hints |
| `Synthadoc: Run lint` | Queues a lint job; shows a notice with contradiction + orphan counts when complete |
| `Synthadoc: Run lint with auto-resolve` | Same as above but passes `auto_resolve: true` — LLM resolves contradictions automatically when confidence ≥ threshold |
| `Synthadoc: List jobs...` | Modal with status-filter dropdown, results table, error details |
| `Synthadoc: Web search...` | Live-polling modal — type a plain topic; set max results (1–50, default 20) and poll interval (500–10000 ms, default 2000 ms); shows phase text, pages list, and URL errors in real time as fan-out jobs complete |

### Ribbon icon

The Synthadoc ribbon icon (a book icon — `synthadoc-ribbon-icon`) appears in the **left sidebar ribbon** of Obsidian, alongside other plugin icons. Click it to open the engine status at a glance.

Shows engine health and live page count: `✅ online · 12 pages` or `❌ offline — run 'synthadoc serve'`.
Calls `GET /health` and `GET /status` in parallel (`Promise.allSettled`).

If the icon is not visible, make sure the plugin is enabled under **Settings → Community plugins** and that you are looking at the left ribbon (not the right sidebar). You can also pin it via right-clicking the ribbon area.

### Settings

| Setting | Default | Description |
|---------|---------|-------------|
| Server URL | `http://127.0.0.1:7070` | HTTP server for this vault |
| Raw sources folder | `raw_sources` | Folder scanned by "Ingest all sources" |

### Supported ingest formats

`.md`, `.txt`, `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.csv`, `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.tiff`

---

## 9. CLI


The CLI is a thin HTTP client — it posts jobs to the running server and polls for results. No LLM agents run in the CLI process.

**File:** `synthadoc/cli/main.py` + subcommands in `synthadoc/cli/`

### Command tree

```
synthadoc
├── install <name> --target <dir> [--demo] [--domain <str>] [--port <N>]
├── uninstall <name>
├── scaffold [-w wiki]
├── demo list
├── serve [-w wiki] [--port N] [--background] [--mcp-only] [--http-only] [--verbose]
├── ingest <source> [-w wiki] [--batch] [--file manifest] [--force] [--analyse-only] [--max-results N]
├── query "<question>" [-w wiki] [--save] [--timeout N]
├── lint
│   ├── run [-w wiki] [--scope contradictions|orphans|all] [--auto-resolve]
│   └── report [-w wiki]
├── jobs
│   ├── list [-w wiki] [--status pending|completed|failed|dead]
│   ├── status <id> [-w wiki]
│   ├── retry <id> [-w wiki]
│   ├── delete <id> [-w wiki]
│   ├── cancel [-w wiki] [--yes]
│   └── purge --older-than <days> [-w wiki]
├── audit
│   ├── history [-w wiki] [--limit N] [--json]   — ingest records: timestamp, source, page, tokens, cost
│   ├── cost [-w wiki] [--days N] [--json]        — token totals + daily breakdown (cost always $0.00 in v0.1)
│   └── events [-w wiki] [--limit N] [--json]    — audit events: timestamp, job_id, event type, metadata
├── status [-w wiki]
├── cache clear [-w wiki]
└── schedule
    ├── add --op "<cmd>" --cron "<expr>" [-w wiki]
    ├── list [-w wiki]
    ├── remove <id> [-w wiki]
    └── apply [-w wiki]
```

### `query` options

| Flag | Default | Description |
|------|---------|-------------|
| `--save` | off | Save the answer as a new wiki page |
| `--timeout N` | `60` | Seconds to wait for the LLM response. Increase for slower providers (e.g. `--timeout 120` for MiniMax reasoning models) |

### `ingest --analyse-only`

Runs the analysis step only (entity extraction + tagging + summary) and prints the JSON result without writing any wiki pages. Useful for previewing how a source will be interpreted before committing it to the wiki.

`--analyse-only` works with all three ingest modes — single source, `--batch`, and `--file` manifest. Each source is analysed in turn and its result printed as JSON:

```bash
# Single file
synthadoc ingest report.pdf --analyse-only -w my-wiki
# → {"entities": ["Alan Turing", "Enigma"], "tags": ["cryptography"], "summary": "…"}

# Whole folder — analyses every supported file, no pages written
synthadoc ingest --batch raw_sources/ --analyse-only -w my-wiki

# Manifest — analyses each line in the file
synthadoc ingest --file sources.txt --analyse-only -w my-wiki
```

### `audit` sub-commands

Query the append-only `audit.db` directly from the CLI:

```bash
# Last 20 ingest records
synthadoc audit history -w my-wiki

# Token spend + cost for the last 30 days (default) or custom window
synthadoc audit cost -w my-wiki
synthadoc audit cost --days 7 -w my-wiki

# Last 100 audit events (contradictions found, auto-resolutions, cost gate triggers)
synthadoc audit events -w my-wiki
```

### Wiki targeting

The `-w` / `--wiki` option accepts either a **registry name** (registered via `install`) or a **filesystem path**. Without `-w`, defaults to the current working directory.

Registry stored at `~/.synthadoc/wikis.json`:

```json
{
  "my-wiki": "/home/user/wikis/my-wiki",
  "research": "/home/user/wikis/research"
}
```

### Wiki context resolution

Every CLI command resolves the target wiki through a priority chain rather than
requiring `-w` on each invocation:

1. **Explicit `-w <name>`** — highest priority, always wins
2. **`SYNTHADOC_WIKI` environment variable** — shell-session scope
3. **`~/.synthadoc/default_wiki`** — persistent default, set by `synthadoc use <name>`
4. **Current directory fallback** — if `.synthadoc/config.toml` is present in CWD
   (backward compat for users who `cd` into a wiki directory)
5. **Error** — actionable message directing user to `synthadoc use`

All hint and notification messages are written to **stderr**. Stdout carries only
command results, keeping `synthadoc ... | jq` and other pipelines clean.

The `synthadoc use` command manages the saved default. `synthadoc use` (no args)
shows which wiki is active and from which source, equivalent to `kubectl config current-context`.

### Error codes

Every user-facing error carries a stable code in the format `[ERR-<CATEGORY>-<NNN>]`. Codes are printed to stderr and embedded in job `error` fields, making them greppable in logs.

**File:** `synthadoc/errors.py`

| Code | Meaning |
|------|---------|
| `ERR-SRV-001` | No server listening for the requested wiki |
| `ERR-SRV-002` | Port already bound by another process |
| `ERR-SRV-003` | Server returned a 4xx/5xx HTTP response |
| `ERR-SRV-004` | Background server process exited immediately |
| `ERR-WIKI-001` | Wiki root directory does not exist |
| `ERR-WIKI-002` | Directory exists but missing `wiki/` subfolder |
| `ERR-WIKI-003` | `wiki/` directory is not writable |
| `ERR-WIKI-004` | Install target already exists on disk |
| `ERR-WIKI-005` | Unknown demo template name |
| `ERR-WIKI-006` | Name not in `~/.synthadoc/wikis.json` |
| `ERR-CFG-001` | Required API key environment variable not set |
| `ERR-CFG-002` | Provider name not recognised |
| `ERR-SKILL-001` | No skill matched the source string |
| `ERR-SKILL-002` | Required pip package for skill not installed |
| `ERR-SKILL-003` | URL returned 403 (bot/paywall protection) |
| `ERR-SKILL-004` | `TAVILY_API_KEY` not set for web search |
| `ERR-INGEST-001` | Source file or directory not found |
| `ERR-INGEST-002` | Source file exists but is empty |
| `ERR-INGEST-003` | `--batch` target is not a directory |
| `ERR-JOB-001` | Job ID does not exist in `jobs.db` |

**CLI errors** go through the `cli_error(code, message, hint)` helper, which prints `[ERR-XXX-NNN] message` to stderr with an optional hint line and exits with code 1. **Agent and skill errors** embed the code directly in the exception message string so it surfaces in the job `error` field.

---

## 10. Configuration

### Resolution order

```
Per-agent override  →  [agents].default (project)  →  [agents].default (global)  →  error
```

Project config wins over global config. Unspecified keys inherit from global defaults.

### Global config — `~/.synthadoc/config.toml`

```toml
[agents]
default = { provider = "anthropic", model = "claude-opus-4-6" }
lint    = { model = "claude-haiku-4-5-20251001" }

[wikis]
research = "~/wikis/research"

[observability]
exporter      = "file"                    # or "otlp"
otlp_endpoint = "http://localhost:4317"   # used when exporter = "otlp"
```

### Provider switching

All seven supported providers (`anthropic`, `openai`, `gemini`, `groq`, `minimax`, `deepseek`, `ollama`) share the same config key. Gemini, Groq, MiniMax, and DeepSeek use OpenAI-compatible endpoints internally, so no custom provider class is needed — just set the provider name and supply the corresponding API key:

```toml
# Switch from Claude to Gemini Flash (free tier available)
[agents]
default = { provider = "gemini", model = "gemini-2.5-flash" }
```

Required environment variables per provider:

| Provider | Env var | Free tier | Vision |
|----------|---------|-----------|--------|
| `anthropic` | `ANTHROPIC_API_KEY` | No (pay-per-token) | Yes |
| `openai` | `OPENAI_API_KEY` | No (pay-per-token) | Yes |
| `gemini` | `GEMINI_API_KEY` | **Yes** — 15 RPM / 1M tokens/day on Flash | Yes |
| `groq` | `GROQ_API_KEY` | **Yes** — generous free tier on Llama/Mixtral models | No |
| `minimax` | `MINIMAX_API_KEY` | No (pay-per-token) | Yes (M2.5 / M2.7 natively multimodal) |
| `deepseek` | `DEEPSEEK_API_KEY` | No (pay-per-token, very cheap) | No (text-only) |
| `ollama` | _(none)_ | **Yes** — fully local | Model-dependent |

### Per-project config — `<wiki-root>/.synthadoc/config.toml`

```toml
[server]
port = 7070

[agents]
default = { provider = "anthropic", model = "claude-opus-4-6" }
lint    = { model = "claude-haiku-4-5-20251001" }
skill   = { model = "claude-haiku-4-5-20251001" }
# llm_timeout_seconds = 90  # set for reasoning models to fail fast instead of silent empty response

[queue]
max_parallel_ingest  = 4
max_retries          = 3
backoff_base_seconds = 5

[cost]
soft_warn_usd                     = 0.50
hard_gate_usd                     = 2.00
auto_resolve_confidence_threshold = 0.85

[ingest]
max_pages_per_ingest  = 15
chunk_size            = 1500
chunk_overlap         = 150
fetch_timeout_seconds = 30   # seconds to wait for a URL response before retrying

[logs]
level        = "INFO"
max_file_mb  = 5
backup_count = 5

[hooks]
on_ingest_complete = "python hooks/auto_commit.py"                        # non-blocking
on_lint_complete   = { cmd = "python hooks/notify.py", blocking = true }  # blocking

[web_search]
provider    = "tavily"   # only supported provider
max_results = 20         # URLs returned per query; each enqueued as an ingest job

# Cron format: minute hour day-of-month month day-of-week
#              0-59   0-23 1-31         1-12  0-6 (0=Sun)

[[schedule.jobs]]
op   = "ingest --batch raw_sources/"
cron = "0 2 * * *"   # every day at 02:00

[[schedule.jobs]]
op   = "lint"
cron = "0 3 * * 0"   # every Sunday at 03:00
```

### Config keys reference

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `agents.default.provider` | str | `"gemini"` | LLM provider: `anthropic`, `openai`, `gemini`, `groq`, `minimax`, `deepseek`, `ollama` |
| `agents.default.model` | str | `"gemini-2.5-flash"` | Model ID |
| `agents.llm_timeout_seconds` | int | `0` | Per-call LLM timeout in seconds; `0` = no limit. Set to e.g. `90` when using reasoning models (MiniMax-M2.5, DeepSeek-R1) that can exceed their internal generation budget silently. Restart required. |
| `server.port` | int | `7070` | HTTP listen port |
| `queue.max_parallel_ingest` | int | `4` | Max concurrent ingest agents |
| `queue.max_retries` | int | `3` | Retries before job → dead |
| `queue.backoff_base_seconds` | int | `5` | Exponential backoff base (±20% jitter) |
| `cache.version` | str | `"4"` | Bump to invalidate all cached LLM responses without touching source code |
| `cost.soft_warn_usd` | float | `0.50` | Log warning, continue _(configured but not yet enforced — cost_guard is wired to the config but check() is not called in the ingest path)_ |
| `cost.hard_gate_usd` | float | `2.00` | Require explicit confirmation _(configured but not yet enforced — see above)_ |
| `cost.auto_resolve_confidence_threshold` | float | `0.85` | Auto-apply lint resolutions above this score |
| `ingest.max_pages_per_ingest` | int | `15` | Max pages one ingest may update |
| `ingest.chunk_size` | int | `1500` | Text chunk size (characters) |
| `ingest.chunk_overlap` | int | `150` | Overlap between chunks |
| `ingest.fetch_timeout_seconds` | int | `30` | Seconds to wait for a URL response before retrying |
| `logs.level` | str | `"INFO"` | Console log level |
| `logs.max_file_mb` | int | `5` | Rotate `synthadoc.log` at this size |
| `logs.backup_count` | int | `5` | Rotated files to keep |
| `web_search.provider` | str | `"tavily"` | Web search provider (currently only `tavily` supported) |
| `web_search.max_results` | int | `20` | Maximum results fetched per web search query |
| `search.vector` | bool | `false` | Enable semantic re-ranking; downloads `BAAI/bge-small-en-v1.5` (~130 MB) once on first enable |
| `search.vector_top_candidates` | int | `20` | BM25 candidate pool size when vector re-ranking is active |

---

## 11. Hook System

Hooks are shell commands executed when lifecycle events fire. They are configured in `.synthadoc/config.toml` under `[hooks]` and receive a JSON context object on stdin.

### Configuration

```toml
# .synthadoc/config.toml

[hooks]
on_ingest_complete = "python scripts/auto_commit.py"                        # non-blocking
on_lint_complete   = { cmd = "python scripts/notify.py", blocking = true }  # blocking
```

### Blocking vs. non-blocking

- **Non-blocking** (default): runs in a background thread; failures are logged but do not affect the operation.
- **Blocking**: must exit `0` for the operation to succeed; a non-zero exit code raises an error and surfaces it to the caller.

### Events

Two events are fired in v0.1:

| Event | Fires when | Context fields |
|-------|-----------|----------------|
| `on_ingest_complete` | A source is successfully ingested | `event`, `wiki`, `source`, `pages_created`, `pages_updated`, `pages_flagged`, `tokens_used`, `cost_usd` |
| `on_lint_complete` | A lint run finishes | `event`, `wiki`, `contradictions_found`, `orphans` |

### Context JSON examples

**on_ingest_complete**
```json
{
  "event": "on_ingest_complete",
  "wiki": "/home/user/wikis/my-wiki",
  "source": "report.pdf",
  "pages_created": ["alan-turing"],
  "pages_updated": ["computing-history"],
  "pages_flagged": [],
  "tokens_used": 4820,
  "cost_usd": 0.031
}
```

**on_lint_complete**
```json
{
  "event": "on_lint_complete",
  "wiki": "/home/user/wikis/my-wiki",
  "contradictions_found": 2,
  "orphans": ["stub-page", "draft-notes"]
}
```

### Hook library

The [`hooks/`](../hooks/) folder in the repository is a community-maintained
library of ready-to-use scripts. Copy a script to your wiki root and configure
it in `config.toml`.

**Writing a hook script:**

- Read context from `sys.stdin` (JSON) — never from files or env vars
- Write human-readable status to `sys.stderr` (not stdout)
- Exit `0` on success, non-zero on failure
- Include the standard header block (event, description, setup instructions)

See [`hooks/README.md`](../hooks/README.md) for contribution guidelines and
the full list of available scripts.

---

## 12. Cache System

Three independent cache layers:

### Layer 1 — Embedding cache (`embeddings.db`)

Stores the BM25 index entry for each wiki page, keyed by page content SHA-256. When a page is updated, only that page's entry is refreshed.

### Layer 2 — LLM response cache (`cache.db`)

Stores deterministic LLM responses keyed by a hash of the operation type and full input text. Enables zero-token lint runs on unchanged pages.

**Cache key:**

```python
def make_cache_key(operation: str, inputs: dict, version: str = CACHE_VERSION) -> str:
    payload = {"v": version, "op": operation, "inputs": inputs}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return digest[:32]
```

The version is part of every cache key, so bumping it causes all existing entries to be bypassed (they remain in `cache.db` but no longer match any key).

To invalidate the cache without touching source code, set `version` in `.synthadoc/config.toml`:

```toml
[cache]
version = "5"   # bump to bypass all entries cached under previous versions
```

The default (`"4"`) is defined in `synthadoc/core/cache.py`. Custom skill authors and wiki operators can bump this freely without modifying core code.

**Invalidation triggers:**

| Trigger | Behavior |
|---------|----------|
| Source content changes | New SHA-256 → cache miss → fresh LLM call |
| `[cache] version` bumped in config | All old entries bypassed |
| `ingest --force` | `bust_cache=True` → skips `cache.get()`, repopulates |
| `cache clear` | Deletes all rows from `cache.db` |

### Layer 3 — Provider prompt cache

Anthropic, OpenAI, and compatible providers cache stable prompt segments server-side. Long system prompts and `AGENTS.md` content hit this cache on repeated calls, giving 50–90% token savings.

**Target cache hit rate:** > 80% on repeated lint runs across unchanged pages.

---

## 13. Cost Guard

**File:** `synthadoc/core/cost_guard.py`

Enforces per-operation budget limits. Evaluated before every LLM call.

### Thresholds

| Threshold | Default | Behaviour |
|-----------|---------|-----------|
| `soft_warn_usd` | $0.50 | Log warning; auto-continue |
| `hard_gate_usd` | $2.00 | Prompt user `Proceed? [y/N]`; block if N; skip prompt if `auto_confirm=True` or `--yes` flag |

### Cost Tracking and Pricing

**How cost is computed (v0.2.0+):**

```
LLM call → CompletionResponse(input_tokens, output_tokens)
             ↓
         estimate_cost(model, input_tokens, output_tokens, is_local)
             ↓
         pricing table lookup in synthadoc/providers/pricing.py
             ↓
         IngestResult.cost_usd  or  audit.db queries.cost_usd
```

**Pricing table (`synthadoc/providers/pricing.py`):**

A static Python dict maps model name → `(input_usd_per_token, output_usd_per_token)`.
Separate input and output rates reflect real-world API pricing (output tokens cost 3–5× more than input tokens for most models).

| Provider | Example model | Input (per token) | Output (per token) |
|---|---|---|---|
| Anthropic | claude-haiku-4-5-20251001 | $0.000001 | $0.000005 |
| Anthropic | claude-sonnet-4-6 | $0.000003 | $0.000015 |
| OpenAI | gpt-4o-mini | $0.00000015 | $0.0000006 |
| Gemini | gemini-2.5-flash | $0.0000003 | $0.0000025 |
| Groq | llama-3.3-70b-versatile | $0.00000059 | $0.00000079 |
| MiniMax | MiniMax-M2.5 | $0.00000015 | $0.0000012 |
| MiniMax | MiniMax-M2.7 | $0.0000003 | $0.0000012 |

**Special cases:**
- **Ollama (local inference):** Always `$0.00` regardless of token count — `is_local=True` short-circuits the calculation.
- **Unknown models:** Use a conservative fallback rate (`$0.000003` per token for both input and output) rather than crashing or silently reporting `$0.00`.

**Token propagation:**

- `CompletionResponse` (already in v0.1) carries `input_tokens` and `output_tokens` from every provider.
- `QueryResult` gains `input_tokens` and `output_tokens` fields (v0.2.0); `Orchestrator.query()` calls `estimate_cost()` to compute `cost_usd` before writing to `audit.db`.
- `IngestResult` gains `input_tokens` and `output_tokens` fields (v0.2.0); `Orchestrator._run_ingest()` calls `estimate_cost()` after ingest completes.
- The vision call and analysis call in `IngestAgent` also accumulate tokens; the analysis call only has a total (split not available due to internal caching).

**Refresh cadence:** The pricing table is refreshed at each major release. `_LAST_UPDATED` in `pricing.py` records the date of last review. See `CONTRIBUTING.md` for the release checklist.

### API

```python
class CostEstimate:
    tokens: int
    cost_usd: float
    operation: str

class CostGuard:
    def check(
        self,
        estimate: CostEstimate,
        auto_confirm: bool = False,   # HTTP server / batch: always proceed
        interactive: bool = True,     # CLI: prompt; HTTP server: False
    ) -> None: ...
```

The HTTP server always passes `auto_confirm=True` (no interactive terminal available). The CLI passes `interactive=True`.

---

## 14. Job Queue

**File:** `synthadoc/core/queue.py`  
**Storage:** `<wiki-root>/.synthadoc/jobs.db` (SQLite)

### State transitions

```
pending → in_progress → completed
                      → failed    (non-retryable error; permanent, no retry)
                      → pending   (retryable error; retries < max_retries, after backoff)
                      → dead      (retryable error; retries == max_retries)
                      → skipped   (deliberately not retried; e.g. auto-blocked domain)
```

| Status | Meaning | Action |
|--------|---------|--------|
| `failed` | Non-retryable error (e.g. stub skill, bad source) | Inspect error; fix source; enqueue again |
| `dead` | Retryable error exhausted max retries | `synthadoc jobs retry <id>` to reset to pending |
| `skipped` | Permanently skipped without retry (e.g. domain auto-blocked after 403) | No action needed; remove from blocked list to re-enable |

**Backoff formula:** `backoff_base_seconds × 2^(retry_count) × jitter`  
where `jitter ∈ [0.8, 1.2]` (±20% random). Applied only to retryable errors (LLM API timeouts, 5xx responses).

**Persistence:** Jobs survive server restarts. `in_progress` jobs at shutdown are reset to `pending` on startup.

---

## 15. Observability and Logging

**Files:** `synthadoc/core/logging_config.py`, `synthadoc/observability/telemetry.py`

### Handler stack

```
Root logger (level: DEBUG)
├── Console handler
│   Level  : cfg.logs.level (default INFO); overridden to DEBUG if --verbose
│   Format : "HH:MM:SS LEVEL  logger — message"
│   Target : stderr
│   Note   : suppressed when --background spawns the detached child process
│
└── File handler (RotatingFileHandler)
    Level  : DEBUG always
    Format : JSON lines
    Target : <wiki-root>/.synthadoc/logs/synthadoc.log
    Rotate : cfg.logs.max_file_mb MB; cfg.logs.backup_count old files kept
```

Suppressed to WARNING: `httpx`, `httpcore`, `uvicorn.access`, `anthropic`, `openai`.

**Background mode (`--background` / `-b`):** the parent process prints the startup banner, spawns a detached child process (`pythonw.exe` on Windows, `start_new_session=True` on Unix), and exits — returning the shell to the user. The child runs without a console handler; all output goes to the file handler only. PID is written to `<wiki-root>/.synthadoc/server.pid`.

### Log record fields

| Field | Always present | Source |
|-------|---------------|--------|
| `ts` | Yes | `record.created` |
| `level` | Yes | `record.levelname` |
| `logger` | Yes | `record.name` |
| `msg` | Yes | `record.getMessage()` |
| `job_id` | Job context only | `LoggerAdapter.extra` |
| `operation` | Job context only | `LoggerAdapter.extra` |
| `wiki` | Job context only | `LoggerAdapter.extra` |
| `trace_id` | When OTel active | OTel span context |

### Job-scoped logging

```python
from synthadoc.core.logging_config import get_job_logger

log = get_job_logger(__name__, job_id="abc123", operation="ingest", wiki="my-wiki")
log.info("Page created: %s", slug)
# → {"ts": "…", "level": "INFO", "logger": "…", "msg": "Page created: alan-turing",
#    "job_id": "abc123", "operation": "ingest", "wiki": "my-wiki"}
```

### Setup (called once at server start)

```python
from synthadoc.core.logging_config import setup_logging
setup_logging(wiki_root=Path("/path/to/wiki"), cfg=config.logs, verbose=False)
```

Idempotent — safe to call multiple times (subsequent calls are no-ops).

### OpenTelemetry

Default: file exporter writing to `traces.jsonl`. Switch to any OTLP backend:

```toml
[observability]
exporter      = "otlp"
otlp_endpoint = "http://localhost:4317"
```

Spans cover: full operation tree (orchestrator → agent → LLM calls → storage writes), with token counts, cost, and cache hit/miss as span attributes.

### Log level guidance

| Level | When to use |
|-------|------------|
| `DEBUG` | LLM prompt bodies, cache key details, BM25 scores, entity extraction details |
| `INFO` | Job lifecycle, page created/updated, server started, lint summary |
| `WARNING` | Soft failures (network unreachable), suspicious patterns |
| `ERROR` | Job failed, API error, file write failed |
| `CRITICAL` | Server cannot start |

---

## 16. Security

### Path traversal

`WikiStorage` normalizes all paths with `Path.resolve()` and asserts each is a child of `wiki_root`. Raises `PermissionError` on violation.

### Prompt injection

- LLM output validated against a strict schema; unrecognized keys dropped silently
- Slug blacklist: `wikilinks`, `wiki`, `obsidian`, `dataview`, `index`, `dashboard`, `log`, `audit`, `hooks`, `skills`
- System prompt instructs the model to never follow instructions embedded in source documents

### Network exposure

HTTP and MCP servers bind to `127.0.0.1` at OS socket level. Not configurable. No remote access without a separate reverse proxy (which the user must explicitly set up).

### HTTP DoS

- Body limit: 10 MB (returns 413)
- Concurrent request cap: 20 (asyncio semaphore)
- Request timeout: 60 seconds

### Audit trail

`audit.db` is append-only in normal operation. The only deletion command is `jobs purge --older-than <days>`, which only removes records older than the given threshold.

### Custom skills trust model

Skills in `<wiki-root>/skills/` or `~/.synthadoc/skills/` run in the same Python process. This is intentional — the wiki root is a trusted location, analogous to `~/bin`. Do not point a wiki root at an untrusted directory.

---

## 17. Plugin Development Guide

This section is for developers building custom skills or LLM providers.

### Writing a skill

1. Create a skill folder in `<wiki-root>/skills/` or `~/.synthadoc/skills/`.
2. Add a `SKILL.md` with YAML frontmatter (name, version, entry, triggers, requires).
3. Create `scripts/main.py` and subclass `BaseSkill` from `synthadoc.skills.base` (Apache-2.0 — no AGPL obligation).
4. Implement `extract(source: str) -> ExtractedContent`.

**Folder layout:**
```
slack_export/
  SKILL.md
  scripts/
    main.py
  references/
    format-notes.md   ← optional; load with self.get_resource("format-notes.md")
```

**`SKILL.md`:**
```yaml
---
name: slack_export
version: "1.0"
description: Extract messages from a Slack export ZIP
entry:
  script: scripts/main.py
  class: SlackExportSkill
triggers:
  extensions: [".slack.zip"]
  intents: ["slack export", "slack archive"]
requires: []
---

Loads all JSON channel files from a Slack export ZIP and returns the message text.
```

**`scripts/main.py`:**
```python
# SPDX-License-Identifier: MIT
from synthadoc.skills.base import BaseSkill, ExtractedContent

class SlackExportSkill(BaseSkill):

    async def extract(self, source: str) -> ExtractedContent:
        import zipfile, json
        messages = []
        with zipfile.ZipFile(source) as zf:
            for name in zf.namelist():
                if name.endswith(".json"):
                    data = json.loads(zf.read(name))
                    for msg in data:
                        if "text" in msg:
                            messages.append(msg["text"])
        return ExtractedContent(
            text="\n".join(messages),
            source_path=source,
            metadata={},
        )
```

**Error handling:** Raise `ValueError` with a clear message if the source cannot be processed. Raise `ImportError` if an optional dependency is missing (the agent will surface a helpful message to the user).

### Writing a provider

Built-in providers: `anthropic`, `openai`, `gemini`, `groq`, `minimax`, `deepseek`, `ollama`. For any provider that exposes an OpenAI-compatible API, no custom class is needed — the built-in `openai` provider with a custom `base_url` is sufficient.

For a fully proprietary API, subclass `LLMProvider`:

```python
# SPDX-License-Identifier: MIT
from synthadoc.providers.base import LLMProvider, Message, CompletionResponse

class MyProvider(LLMProvider):

    async def complete(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.0,
        **kwargs,
    ) -> CompletionResponse:
        # Call your API …
        return CompletionResponse(
            text="…",
            input_tokens=N,
            output_tokens=M,
        )
```

Place in `~/.synthadoc/providers/` or the wiki `providers/` directory. Reference by name in config:

```toml
[agents]
default = { provider = "my_provider", model = "my-model-id" }
```

### Writing a hook

Hooks can be in any language. They receive JSON on stdin and must exit 0 on success.

```bash
#!/usr/bin/env bash
# hooks/notify.sh
context=$(cat)
event=$(echo "$context" | jq -r '.event')
wiki=$(echo "$context" | jq -r '.wiki')
echo "Event $event fired on wiki $wiki" | mail -s "Synthadoc notification" you@example.com
```

---

## Appendix A — Release Feature Index

### v0.1.0 (Community Edition)

- **3 agents** — IngestAgent (two-step cached synthesis), QueryAgent (BM25 + LLM), LintAgent (contradiction + orphan detection + auto-resolution)
- **8 built-in skills** — PDF, URL, Markdown/TXT, DOCX, PPTX, XLSX/CSV, Image (vision), Web search (Tavily)
- **Folder-based skill system** — each skill is a self-contained folder with a `SKILL.md` manifest; intent-based dispatch alongside extension matching; drop a folder in `skills/` to add a new format without touching core code
- **2 access surfaces** — CLI (thin HTTP client), HTTP REST API
- **Obsidian plugin** — ingest (file picker, URL, all sources, web search), query modal, lint report, jobs list — all from the command palette; ribbon shows engine health + page count
- **7 LLM providers** — Anthropic, OpenAI, Gemini (free tier), Groq (free tier), MiniMax (paid, multimodal), DeepSeek (paid, very cheap text-only), Ollama (local); switch with one config line
- **Two-step ingest** — `_analyse()` caches entity extraction + summary; decision prompt uses summary instead of full text; reduces cost on large documents
- **purpose.md scope filtering** — define what belongs in your wiki; the LLM skips out-of-scope sources cleanly
- **overview.md auto-summary** — 2-paragraph wiki overview regenerated automatically after every ingest
- **Audit CLI** — `synthadoc audit history / cost / events` query `audit.db`; `--analyse-only` flag previews ingest analysis before writing pages
- **3-layer cache** — embedding cache, LLM response cache, provider prompt cache
- **Cost guards** — configurable soft-warn and hard-gate USD thresholds
- **Hook system** — shell commands on `on_ingest_complete` and `on_lint_complete` lifecycle events; blocking or background; context passed as JSON on stdin
- **Job queue** — SQLite-backed, persistent, retry with exponential backoff; `failed` vs `dead` status distinction
- **Multi-wiki** — unlimited isolated wikis, each on its own port
- **OpenTelemetry** — traces, metrics, structured logs; OTLP export optional
- **Cross-platform** — Windows, Linux, macOS

### v0.2.0

- **Query decomposition** — `QueryAgent.decompose()` breaks complex questions into 1–N focused sub-questions (cap=4); parallel BM25 search per sub-question; merged and deduplicated by highest score; graceful fallback on LLM error; markdown fence stripping for cross-model robustness
- **Query audit trail** — `queries` table in `audit.db`; every query recorded with question text, sub-question count, tokens, cost, timestamp; `cost_summary()` now aggregates ingest + query spend; exposed via `GET /audit/queries`, `synthadoc audit queries`, and Obsidian "Audit: query history..." command
- **Per-model cost tracking** — per-token rate table covers all 5 providers; cost calculated for both ingest and query operations and stored in `audit.db`; Ollama records no API cost (local model); unknown models use a conservative fallback rate; exposed via `audit cost` CLI and `GET /audit/costs`
- **Knowledge gap detection** — three independent signals (too few pages, low BM25 max score, low content-overlap page count); query result carries a gap flag and targeted ingest suggestions when the wiki lacks relevant coverage; displayed as an Obsidian callout block in the plugin and CLI output
- **BM25 in-memory corpus cache** — `HybridSearch._cached_corpus` built once per session, invalidated via `invalidate_index()` after each page write; eliminates N×disk reads on decomposed queries
- **OpenAIProvider contract tests** — 4 tests covering happy path, system message, null content, and custom `base_url` forwarding; applies to OpenAI, Gemini, Groq, and Ollama (all use `OpenAIProvider`)
- **HTTP 502 on LLM failure** — `/query` GET and POST return 502 Bad Gateway (not raw 500) when the LLM provider is unreachable
- **Web search decomposition** — `SearchDecomposeAgent` breaks a web search intent into 1–4 focused keyword search strings (separate prompt from query decomposition); parallel Tavily searches; URL deduplication; graceful fallback on LLM error; integrated into `IngestAgent` at the web search fan-out point
- **New Obsidian commands (8 added, 15 total)** — `Lint: run`, `Lint: run with auto-resolve`, `Jobs: retry dead job...`, `Jobs: purge old completed/dead...`, `Wiki: regenerate scaffold...`, `Audit: ingest history...`, `Audit: cost summary...`, `Audit: query history...`
- **Vector search + semantic re-ranking** — opt-in hybrid BM25 + local vector search using `BAAI/bge-small-en-v1.5` via `fastembed`; one-time background migration embeds existing pages; BM25 serves during migration; enable with `[search] vector = true`
- **Obsidian web search live view** — `WebSearchModal` replaced with live-polling panel that shows phase text, pages list, and URL errors in real time; configurable poll interval; modal stays open until all fan-out URL jobs settle; job progress tracked via new `progress` column in `jobs.db`
- **Web search URL cap** — `synthadoc ingest "search for: …" --max-results N` limits total URLs enqueued across all sub-queries; Obsidian modal exposes the same as a numeric input (1–50, default 20); cap applied after dedup
- **Image ingest for OpenAI-compatible providers** — `OpenAIProvider` auto-converts Anthropic image blocks to OpenAI `image_url` format; Groq flagged as non-vision (`supports_vision = False`); image jobs routed to Groq get `fail_permanent` with a clear message
- **Job crash recovery** — `in_progress` jobs are reset to `pending` on server `init()`, so all pending work resumes automatically after a restart
- **Rate-limit requeue** — HTTP 429 responses from any LLM provider are detected and requeued via `requeue()` (retry counter unchanged), preserving the retry budget for real errors
- **Bulk cancel (`jobs cancel`)** — `synthadoc jobs cancel [-w wiki] [--yes]` marks all pending jobs as `skipped` in one operation; also `POST /jobs/cancel-pending`

### v0.3.0

- **Session wiki resolution (`synthadoc use`)** — `synthadoc use <name>` writes the default wiki to `~/.synthadoc/default_wiki`; all commands resolve it automatically via priority chain: `-w` flag > `SYNTHADOC_WIKI` env var > saved default > CWD fallback; hint messages simplified to `[wiki: <name>]`; `-w .` omitted from job hints when CWD is the active wiki
- **MiniMax reasoning-model fixes** — `OpenAIProvider` now handles three failure modes of reasoning models (e.g. MiniMax-M2.5): (1) `choices=null` response converted from silent `TypeError` to a descriptive `RuntimeError` with error code logged; (2) `content=null` with prose answer in `reasoning_content` — think-tag stripping then full-text fallback so query synthesis returns a real answer; (3) `APITimeoutError` caught, logged with the config key to set, then re-raised
- **Configurable LLM call timeout (`agents.llm_timeout_seconds`)** — new `[agents]` key (default `0` = no limit); passed as `timeout` to every OpenAI-compatible `create()` call; `APITimeoutError` logs an actionable message naming the exact config key; config.toml template ships the key commented out with a 5-line explanation of when to enable it
- **`parse_json_string_array` utility** — extracted shared fence-strip + JSON-parse + filter logic from `QueryAgent.decompose()` and `SearchDecomposeAgent.decompose()` into `synthadoc/agents/_utils.py`; 16 unit tests; LLM call failures and JSON-parse failures now log separate, distinct messages
- **DeepSeek provider** — `deepseek` added as an eighth provider; routes through `OpenAIProvider` with `base_url="https://api.deepseek.com/v1"` and `DEEPSEEK_API_KEY`; vision disabled (`_NO_VISION_HOSTS`); DeepSeek-R1 `<think>` tags in the `content` field are stripped by the existing regex; config.toml template ships a commented-out example for `deepseek-chat`
- **v0.2.0 gap fixes** — Ollama `eval_count` mapped to `output_tokens` (was always 0); `_SLUG_BLACKLIST` moved to module-level `frozenset`; synthetic URL fields in ingest_agent commented; four test-coverage gaps closed (no-text guard, orphan flag inversion, `/analyse` endpoint, hybrid-search partial-miss fallback)
