# Synthadoc — Design Document

**Version:** 0.1  
**Audience:** Product users who want to understand how the system works; developers adding features, skills, and plugins.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Core Concepts](#2-core-concepts)
3. [System Architecture](#3-system-architecture)
4. [Agents](#4-agents)
5. [Skills System](#5-skills-system)
6. [Storage](#6-storage)
7. [HTTP API](#7-http-api)
8. [MCP Server](#8-mcp-server)
9. [Obsidian Plugin](#9-obsidian-plugin)
10. [CLI](#10-cli)
11. [Configuration](#11-configuration)
12. [Hook System](#12-hook-system)
13. [Cache System](#13-cache-system)
14. [Cost Guard](#14-cost-guard)
15. [Job Queue](#15-job-queue)
16. [Observability and Logging](#16-observability-and-logging)
17. [Security](#17-security)
18. [Plugin Development Guide](#18-plugin-development-guide)
19. [v0.2 Roadmap](#19-v02-roadmap)

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

```
┌──────────────────────────────────────────────────────────────────┐
│  Access layer                                                    │
│                                                                  │
│  synthadoc CLI          Obsidian plugin       Claude Desktop     │
│  (thin HTTP client)     (TypeScript)          (MCP client)       │
└───────┬─────────────────────────┬──────────────────┬────────────┘
        │  HTTP REST              │  HTTP REST        │  MCP stdio
        ▼                         ▼                   ▼
┌──────────────────────────────────────────────────────────────────┐
│  Integration layer                                               │
│                                                                  │
│  FastAPI (http_server.py)            MCP server (mcp_server.py)  │
│  localhost:PORT                      stdio transport             │
│  CORS: obsidian.md, localhost        6 tools                     │
│  10 MB body limit, 60s timeout                                   │
│  Background job worker (2s poll)                                 │
└──────────────────────┬───────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────────┐
│  Core layer                                                      │
│                                                                  │
│  Orchestrator         CostGuard           Scheduler              │
│  ├─ IngestAgent       ├─ soft_warn_usd    ├─ cron expressions    │
│  ├─ QueryAgent        └─ hard_gate_usd    └─ OS task scheduler   │
│  └─ LintAgent                                                    │
│                                                                  │
│  Job Queue (SQLite, asyncio)                                     │
│  Cache (3-layer)                                                 │
│  Hooks dispatcher                                                │
└──────────────────────┬───────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────────┐
│  Skill layer (lazy-loaded)                                       │
│                                                                  │
│  SkillAgent → pdf / url / markdown / docx / xlsx / image         │
│             → custom skills (wiki skills/ or ~/.synthadoc/skills/)│
└──────────────────────┬───────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────────┐
│  Provider layer                                                  │
│                                                                  │
│  Anthropic (claude-opus-4-6)  OpenAI  Ollama  Custom             │
└──────────────────────┬───────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────────┐
│  Storage layer                                                   │
│                                                                  │
│  wiki/*.md  audit.db  jobs.db  cache.db  embeddings.db  logs/    │
└──────────────────────────────────────────────────────────────────┘
```

### Request lifecycle (ingest via CLI)

1. `synthadoc ingest report.pdf -w my-wiki`
2. CLI posts `POST /jobs/ingest {source: "report.pdf"}` to `localhost:7070`
3. HTTP server validates path, writes job to `jobs.db` with status `pending`, returns `{job_id}`
4. Background worker picks up job within 2 seconds
5. Orchestrator instantiates IngestAgent, checks CostGuard
6. SkillAgent detects `.pdf`, lazy-loads `PdfSkill`, extracts text
7. IngestAgent Pass 1: entity extraction → candidate page list
8. IngestAgent Pass 2: BM25 search → candidate pages loaded
9. IngestAgent Pass 3: LLM decides per-page action (create / update / flag / skip)
10. IngestAgent Pass 4: writes pages, fires hooks
11. Job transitions to `completed`; `log.md` updated; `audit.db` record written

---

## 4. Agents

All agents are async Python classes. They receive a job context, write results to storage, and return a summary. Agents never call each other directly — they are dispatched by the Orchestrator.

### IngestAgent

**File:** `synthadoc/agents/ingest_agent.py`

Four-pass pipeline:

| Pass | Model | Purpose |
|------|-------|---------|
| 1 — Entity extraction | Fast (e.g. haiku) | Extract concepts, entities, tags from raw text. Zero wiki reads. |
| 2 — Candidate search | None (BM25) | Find existing pages related to extracted entities |
| 3 — LLM decision | Default | Review candidates + source text. Output per-page action: `create`, `update`, `flag_contradiction`, `skip` |
| 4 — Write | None | Apply actions; update frontmatter; write `[[wikilinks]]`; fire hooks |

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

**File:** `synthadoc/agents/query_agent.py`

1. Extract search terms from the natural language question
2. BM25 search against wiki
3. LLM synthesizes answer from retrieved pages, citing `[[page-name]]` sources
4. Optional: save answer as a new wiki page

### LintAgent

**File:** `synthadoc/agents/lint_agent.py`

Runs against the entire wiki or a scoped subset:

| Check | What it finds |
|-------|---------------|
| Contradiction | Pages with `status: contradicted` |
| Orphan | Pages with zero inbound `[[wikilinks]]` |
| Stale | Pages whose `sources[]` entries no longer exist on disk |
| Missing link | Entity mentioned in page body but no wikilink created |

**Auto-resolution:** For contradictions, LintAgent asks the LLM to propose a resolution with a confidence score. If score ≥ `auto_resolve_confidence_threshold` (default 0.85), applies automatically. Below threshold, queues for human review.

**Index suggestion:** For orphan pages, LintAgent reads the page frontmatter and generates a ready-to-paste `wiki/index.md` entry: `- [[slug]] — tag1, tag2, tag3`.

### SkillAgent

**File:** `synthadoc/agents/skill_agent.py`

Dispatches to the correct skill based on file extension, URL prefix, or intent keyword match. Manages 3-tier lazy loading. Returns `ExtractedContent` to IngestAgent.

URL and intent-based sources (e.g. `search for: Dennis Ritchie…`) bypass all file-system existence checks in IngestAgent. Only local-file sources are checked for path validity and hashed for dedup.

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
| `xlsx` | `.xlsx`, `.csv` | `spreadsheet`, `excel`, `csv` | openpyxl |
| `image` | `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.tiff` | `image`, `screenshot`, `diagram`, `photo` | Base64 + vision LLM |
| `web_search` | _(none)_ | `search for`, `find on the web`, `look up`, `web search`, `browse` | **v0.2 stub** — job set to `failed` immediately, no retry |

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

### jobs.db — Job queue

See [Section 14 — Job Queue](#14-job-queue).

### cache.db — LLM response cache

See [Section 12 — Cache System](#12-cache-system).

### embeddings.db — Search index

BM25 index over all wiki pages. Tokenizer handles ASCII and CJK:

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

**File:** `synthadoc/integration/http_server.py`  
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
| `DELETE` | `/jobs/{id}` | — | `{deleted: bool}` |
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
  "result": {"pages_created": ["alan-turing"], "cost_usd": 0.031},
  "error": null
}
```

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

## 8. MCP Server

**File:** `synthadoc/integration/mcp_server.py`  
**Transport:** stdio (JSON-RPC 2.0)  
**Activation:** `synthadoc serve -w <wiki> --mcp-only`

### Tools

| Tool name | Parameters | Returns | Purpose |
|-----------|-----------|---------|---------|
| `synthadoc_ingest` | `source: str` | `{job_id, source}` | Enqueue ingest job |
| `synthadoc_query` | `question: str` | `{answer, citations: [str]}` | Query + LLM synthesis |
| `synthadoc_lint` | `scope: str = "all"` | `{contradictions_found, orphans}` | Run lint checks |
| `synthadoc_search` | `terms: str` | `{results: [{slug, score, title, snippet}]}` | BM25 search (no LLM) |
| `synthadoc_status` | — | `{pages, wiki, queue_depth}` | Wiki statistics |
| `synthadoc_job_status` | `job_id: str` | `Job` | Poll job by ID |

### Claude Desktop registration

```json
{
  "mcpServers": {
    "synthadoc-my-wiki": {
      "command": "synthadoc",
      "args": ["serve", "--wiki", "my-wiki", "--mcp-only"]
    }
  }
}
```

Register one entry per wiki. Each runs as an isolated MCP server on its own stdio process.

---

## 9. Obsidian Plugin

**Package:** `synthadoc-obsidian` (TypeScript)  
**Location:** `obsidian-plugin/` in the repo  
**Version:** 0.1.0

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
| `Synthadoc: List jobs...` | Modal with status-filter dropdown, results table, error details |
| `Synthadoc: Web search (coming in v0.2)...` | Shows a notice — functionality lands in v0.2 |

### Ribbon icon

Shows engine health and live page count: `✅ online · 12 pages` or `❌ offline — run 'synthadoc serve'`.
Calls `GET /health` and `GET /status` in parallel (`Promise.allSettled`).

### Settings

| Setting | Default | Description |
|---------|---------|-------------|
| Server URL | `http://127.0.0.1:7070` | HTTP server for this vault |
| Raw sources folder | `raw_sources` | Folder scanned by "Ingest all sources" |

### Supported ingest formats

`.md`, `.txt`, `.pdf`, `.docx`, `.xlsx`, `.csv`, `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.tiff`

---

## 10. CLI


The CLI is a thin HTTP client — it posts jobs to the running server and polls for results. No LLM agents run in the CLI process.

**File:** `synthadoc/cli/main.py` + subcommands in `synthadoc/cli/`

### Command tree

```
synthadoc
├── install <name> --target <dir> [--demo]
├── uninstall <name>
├── demo list
├── serve [-w wiki] [--port N] [--mcp-only] [--http-only] [--verbose]
├── ingest <source> [-w wiki] [--batch] [--file manifest] [--force]
├── query "<question>" [-w wiki] [--save]
├── lint
│   ├── run [-w wiki] [--scope contradictions|orphans|all] [--since date] [--auto-resolve]
│   └── report [-w wiki]
├── jobs
│   ├── list [-w wiki] [--status pending|completed|failed|dead]
│   ├── status <id> [-w wiki]
│   ├── retry <id> [-w wiki]
│   ├── delete <id> [-w wiki]
│   └── purge --older-than <days> [-w wiki]
├── search "<terms>" [-w wiki]
├── status [-w wiki]
├── cache clear [-w wiki]
└── schedule
    ├── add --op "<cmd>" --cron "<expr>" [-w wiki]
    ├── list [-w wiki]
    ├── remove <id> [-w wiki]
    └── apply [-w wiki]
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

---

## 11. Configuration

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

### Per-project config — `<wiki-root>/.synthadoc/config.toml`

```toml
[server]
port = 7070

[agents]
default = { provider = "anthropic", model = "claude-opus-4-6" }
lint    = { model = "claude-haiku-4-5-20251001" }
skill   = { model = "claude-haiku-4-5-20251001" }

[queue]
max_parallel_ingest  = 4
max_retries          = 3
backoff_base_seconds = 5

[cost]
soft_warn_usd                     = 0.50
hard_gate_usd                     = 2.00
auto_resolve_confidence_threshold = 0.85

[ingest]
max_pages_per_ingest = 15
chunk_size           = 1500
chunk_overlap        = 150

[logs]
level        = "INFO"
max_file_mb  = 5
backup_count = 5

[hooks]
on_ingest_complete     = "python hooks/auto_commit.py"
on_contradiction_found = { cmd = "python hooks/notify.py", blocking = true }

[[schedule.jobs]]
op   = "ingest --batch raw_sources/"
cron = "0 2 * * *"

[[schedule.jobs]]
op   = "lint"
cron = "0 3 * * 0"
```

### Config keys reference

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `agents.default.provider` | str | `"anthropic"` | LLM provider: `anthropic`, `openai`, `ollama` |
| `agents.default.model` | str | `"claude-opus-4-6"` | Model ID |
| `server.port` | int | `7070` | HTTP listen port |
| `queue.max_parallel_ingest` | int | `4` | Max concurrent ingest agents |
| `queue.max_retries` | int | `3` | Retries before job → dead |
| `queue.backoff_base_seconds` | int | `5` | Exponential backoff base (±20% jitter) |
| `cost.soft_warn_usd` | float | `0.50` | Log warning, continue |
| `cost.hard_gate_usd` | float | `2.00` | Require explicit confirmation |
| `cost.auto_resolve_confidence_threshold` | float | `0.85` | Auto-apply lint resolutions above this score |
| `ingest.max_pages_per_ingest` | int | `15` | Max pages one ingest may update |
| `ingest.chunk_size` | int | `1500` | Text chunk size (characters) |
| `ingest.chunk_overlap` | int | `150` | Overlap between chunks |
| `logs.level` | str | `"INFO"` | Console log level |
| `logs.max_file_mb` | int | `5` | Rotate `synthadoc.log` at this size |
| `logs.backup_count` | int | `5` | Rotated files to keep |

---

## 12. Hook System

Hooks are shell commands executed when lifecycle events fire. They receive a JSON context on stdin.

### Events

| Event | Fires when |
|-------|-----------|
| `on_ingest_complete` | A source is successfully ingested |
| `on_ingest_failed` | An ingest job fails (before retry) |
| `on_contradiction_found` | A contradiction detected during ingest |
| `on_lint_complete` | A lint run finishes |
| `on_query_saved` | A query answer is saved as a wiki page |
| `on_batch_complete` | A full batch ingest completes |
| `on_cost_warning` | Estimated cost crosses `soft_warn_usd` |
| `on_dead_job` | A job exhausts retries |

### Hook locations

1. `<wiki-root>/hooks/` — wiki-specific; both run when same event defined in both locations
2. `~/.synthadoc/hooks/` — global

### Blocking vs. non-blocking

```toml
on_ingest_complete     = "python hooks/auto_commit.py"           # non-blocking
on_contradiction_found = { cmd = "python hooks/alert.py", blocking = true }  # blocking
```

Non-blocking: runs in background thread; failures logged but ignored.  
Blocking: must exit 0 for the operation to complete; non-zero causes operation failure.

### Context JSON (on stdin)

```json
{
  "event": "on_ingest_complete",
  "wiki": "my-wiki",
  "wiki_root": "/home/user/wikis/my-wiki",
  "source": "report.pdf",
  "pages_created": ["alan-turing"],
  "pages_updated": ["computing-history"],
  "pages_flagged": [],
  "tokens_used": 4820,
  "cost_usd": 0.031,
  "cache_hits": 3,
  "timestamp": "2026-04-10T14:32:00Z"
}
```

---

## 13. Cache System

Three independent cache layers:

### Layer 1 — Embedding cache (`embeddings.db`)

Stores the BM25 index entry for each wiki page, keyed by page content SHA-256. When a page is updated, only that page's entry is refreshed.

### Layer 2 — LLM response cache (`cache.db`)

Stores deterministic LLM responses keyed by a hash of the operation type and full input text. Enables zero-token lint runs on unchanged pages.

**Cache key:**

```python
CACHE_VERSION = "4"

def make_cache_key(operation: str, inputs: dict) -> str:
    payload = {"v": CACHE_VERSION, "op": operation, "inputs": inputs}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return digest[:32]
```

Bump `CACHE_VERSION` whenever prompt templates change. Old entries remain in `cache.db` but stop matching keys.

**Invalidation triggers:**

| Trigger | Behavior |
|---------|----------|
| Source content changes | New SHA-256 → cache miss → fresh LLM call |
| `CACHE_VERSION` bumped | All old entries bypassed |
| `ingest --force` | `bust_cache=True` → skips `cache.get()`, repopulates |
| `cache clear` | Deletes all rows from `cache.db` |

### Layer 3 — Provider prompt cache

Anthropic, OpenAI, and compatible providers cache stable prompt segments server-side. Long system prompts and `AGENTS.md` content hit this cache on repeated calls, giving 50–90% token savings.

**Target cache hit rate:** > 80% on repeated lint runs across unchanged pages.

---

## 14. Cost Guard

**File:** `synthadoc/core/cost_guard.py`

Enforces per-operation budget limits. Evaluated before every LLM call.

### Thresholds

| Threshold | Default | Behaviour |
|-----------|---------|-----------|
| `soft_warn_usd` | $0.50 | Log warning; auto-continue |
| `hard_gate_usd` | $2.00 | Prompt user `Proceed? [y/N]`; block if N; skip prompt if `auto_confirm=True` or `--yes` flag |

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

## 15. Job Queue

**File:** `synthadoc/core/queue.py`  
**Storage:** `<wiki-root>/.synthadoc/jobs.db` (SQLite)

### Schema

```sql
CREATE TABLE jobs (
    id          TEXT PRIMARY KEY,
    operation   TEXT NOT NULL,      -- 'ingest' | 'lint' | 'query'
    status      TEXT NOT NULL,      -- 'pending' | 'in_progress' | 'completed' | 'failed' | 'dead'
    payload     TEXT,               -- JSON: operation-specific input
    result      TEXT,               -- JSON: operation-specific output
    error       TEXT,               -- error message + traceback on failure
    retries     INTEGER DEFAULT 0,
    created_at  TEXT NOT NULL       -- UTC ISO-8601
);
```

### State transitions

```
pending → in_progress → completed
                      → failed    (non-retryable error; permanent, no retry)
                      → pending   (retryable error; retries < max_retries, after backoff)
                      → dead      (retryable error; retries == max_retries)
```

| Status | Meaning | Action |
|--------|---------|--------|
| `failed` | Non-retryable error (e.g. stub skill, bad source) | Inspect error; fix source; enqueue again |
| `dead` | Retryable error exhausted max retries | `synthadoc jobs retry <id>` to reset to pending |

**Backoff formula:** `backoff_base_seconds × 2^(retry_count) × jitter`  
where `jitter ∈ [0.8, 1.2]` (±20% random). Applied only to retryable errors (LLM API timeouts, 5xx responses).

**Persistence:** Jobs survive server restarts. `in_progress` jobs at shutdown are reset to `pending` on startup.

---

## 16. Observability and Logging

**Files:** `synthadoc/core/logging_config.py`, `synthadoc/observability/telemetry.py`

### Handler stack

```
Root logger (level: DEBUG)
├── Console handler
│   Level  : cfg.logs.level (default INFO); overridden to DEBUG if --verbose
│   Format : "HH:MM:SS LEVEL  logger — message"
│   Target : stderr
│
└── File handler (RotatingFileHandler)
    Level  : DEBUG always
    Format : JSON lines
    Target : <wiki-root>/.synthadoc/logs/synthadoc.log
    Rotate : cfg.logs.max_file_mb MB; cfg.logs.backup_count old files kept
```

Suppressed to WARNING: `httpx`, `httpcore`, `uvicorn.access`, `anthropic`, `openai`.

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

## 17. Security

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

## 18. Plugin Development Guide

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

```python
# SPDX-License-Identifier: MIT
from synthadoc.providers.base import LLMProvider, Message, CompletionResponse

class GeminiProvider(LLMProvider):

    async def complete(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.0,
        **kwargs,
    ) -> CompletionResponse:
        # Call Gemini API …
        return CompletionResponse(
            content="…",
            usage={"input_tokens": N, "output_tokens": M},
        )
```

Place in `~/.synthadoc/providers/` or the wiki `providers/` directory. Reference by name in config:

```toml
[agents]
default = { provider = "gemini", model = "gemini-2.0-flash" }
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

## 19. v0.2 Roadmap

Planned for release the week of 2026-04-25.

| Feature | Motivation |
|---------|-----------|
| **Web search ingest** | `web_search` skill fully implemented — `synthadoc ingest "search for: <query>"` fetches top results and compiles them into wiki pages |
| **Web UI** | Browser-based dashboard — pages, jobs, contradictions, orphans — without requiring Obsidian |
| **Vector search + re-ranking** | Hybrid BM25 + `fastembed` local vectors; better recall on semantically related queries; `fastembed` already an optional dependency |
| **Graph-aware retrieval** | Traverse wikilink adjacency for multi-hop queries (e.g. "What connects Turing to von Neumann?") |
| **Larger corpus support** | Sharded BM25 index; incremental embedding updates; streaming ingest for very large documents |
| **Additional LLM providers** | Gemini, Mistral, Bedrock — beyond Anthropic, OpenAI, Ollama |
