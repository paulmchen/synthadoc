# Synthadoc

```
      .-+###############+-.
    .##                   ##.
   ##    .----.   .----.    ##
  ##    /######\ /######\    ##
  ##    |######| |######|    ##
  ##    | [SD] | | wiki |    ##
  ##    |######| |######|    ##
  ##    \######/ \######/    ##
   ##    '----'   '----'    ##
    '##                   ##'
      '-+###############+-'

  S Y N T H A D O C  0.1.0
  ────────────────────────────────
  Domain-agnostic LLM wiki engine
```

**Domain-agnostic LLM knowledge compilation engine.**

> Built for individuals, small teams, and large organizations who need a knowledge base that stays accurate as documents accumulate.

Synthadoc reads your raw source documents — PDFs, spreadsheets, web pages, images, Word files — and uses an LLM to synthesize them into a persistent, structured wiki. Cross-references are built automatically, contradictions are detected and surfaced, orphan pages are flagged, and every answer cites its sources. The result lives as plain Markdown in a local folder that opens directly in [Obsidian](https://obsidian.md).

---

## Who Is It For?

Synthadoc scales from a single researcher to a company-wide knowledge platform:

| Team size | Typical use case |
|-----------|-----------------|
| **Solo / 1–2 people** | Personal research wiki, freelance knowledge base, indie hacker documentation — run it free on Gemini Flash or a local Ollama model with zero ongoing cost |
| **Small team (3–20)** | Shared internal wiki for a startup or department; each member ingests from their own sources; the shared wiki stays consistent and contradiction-free |
| **Medium / enterprise** | Compliance-sensitive knowledge bases that must stay local; per-department wikis on separate ports; audit trail for every ingest and cost event; hook system for CI/CD integration; OpenTelemetry for ops dashboards |

No cloud account. No vendor lock-in. The wiki is plain Markdown — open it in any editor, back it up with git, sync it with any cloud drive.

---

## Inspiration and Vision

> *"The LLM should be able to maintain a wiki for you."*
> — Andrej Karpathy, [LLM Wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)

Most knowledge-management tools retrieve and summarize at query time. Synthadoc inverts this: it **compiles knowledge at ingest time**. Every new source enriches and cross-links the entire corpus, not just appends a new chunk. The wiki is the artifact — readable, editable, and browsable without any tool running.

**Long-term alignment:**

| Direction | How Synthadoc moves there |
|-----------|--------------------------|
| Agent orchestration | Orchestrator dispatches parallel IngestAgent, QueryAgent, LintAgent sub-agents with cost guards and retry backoff |
| Sub-agent skills/plugins | 3-tier lazy-load skill system; drop a Python file in `skills/` to add a new file format without touching the core |
| LLM wiki vs. RAG | Pre-compiled structured knowledge beats query-time synthesis for contradiction detection, graph traversal, and offline access |
| MCP / CLI / HTTP | Synthadoc IS an MCP server — Claude Desktop can orchestrate it naturally; CLI and HTTP API support every other integration path |
| Local-first | All data stays on your machine; localhost-only network binding; no cloud dependency except the LLM API itself |
| Provider choice | Five LLM backends including free-tier Gemini and Groq — no single-vendor dependency |

---

## Problems Addressed

### 1. RAG conflates contradictions; Synthadoc surfaces them

When two sources disagree, vector search returns both and the LLM silently blends them. Synthadoc detects the conflict during ingest, flags the page with `status: contradicted`, preserves both claims with citations, and either auto-resolves (if confidence ≥ threshold) or queues the conflict for human review.

### 2. Knowledge fragments; Synthadoc links it

RAG chunks are isolated. Synthadoc builds `[[wikilinks]]` between related pages during every ingest pass. The resulting graph is visible in Obsidian's Graph view and queryable with Dataview.

### 3. Orphan knowledge has no address; Synthadoc finds it

Pages that exist but are referenced by nothing are surfaced by the lint system, with ready-to-paste index entries so you can quickly integrate them.

### 4. Re-synthesis is expensive; Synthadoc caches it

A 3-layer cache (embedding, LLM response, provider prompt cache) means repeated lint runs on unchanged pages cost near-zero tokens.

### 5. Knowledge is locked in tools; Synthadoc escapes it

Every page is a plain Markdown file with YAML frontmatter. No proprietary format. Open the folder in any editor, put it in git, sync it with any cloud drive.

### Business values

| Value | How |
|-------|-----|
| **Faster onboarding** | New team members query the wiki instead of digging through documents |
| **Audit trail** | Every ingest recorded in `audit.db` with source hash, cost, and timestamp |
| **Cost control** | Configurable soft-warn and hard-gate thresholds; 3-layer cache reduces repeat spend |
| **Compliance** | Local-first — source documents and compiled knowledge never leave your machine |
| **Extensibility** | Hooks fire on every event; custom skills load without a server restart |

---

## Why Synthadoc?

### Competitive advantages

| Capability | Synthadoc | Typical RAG | NotebookLM | Notion AI |
|------------|-----------|-------------|------------|-----------|
| Ingest-time synthesis | **Yes** | No | Partial | No |
| Contradiction detection | **Yes** | No | No | No |
| Orphan page detection | **Yes** | No | No | No |
| Persistent wikilink graph | **Yes** | No | No | No |
| Local-first (no cloud data) | **Yes** | Varies | No | No |
| Custom skill plugins | **Yes** | Limited | No | No |
| MCP server built-in | **Yes** | No | No | No |
| Obsidian integration | **Yes** | No | No | No |
| Cost guard + audit trail | **Yes** | No | No | No |
| Hook / CI integration | **Yes** (2 events) | No | No | No |
| Offline browsable artifact | **Yes** | No | No | No |
| Multi-wiki isolation | **Yes** | No | No | No |
| Web search → wiki pages | **Yes** | No | No | No |
| Free LLM tier support | **Yes** (Gemini, Groq) | No | No | No |
| Auto wiki overview page | **Yes** | No | No | No |
| Resumable job queue + retry | **Yes** | No | No | No |

### Key differentiators vs. RAG

RAG chunks documents and retrieves them at query time. Synthadoc **compiles** knowledge: every new source is synthesized into the existing wiki graph at ingest time.

- **Contradictions are caught, not blended.** When two sources disagree, Synthadoc flags the page — RAG silently averages both claims.
- **Knowledge is linked, not scattered.** `[[wikilinks]]` connect related pages into a navigable graph visible in Obsidian and queryable with Dataview.
- **The artifact outlives the tool.** Close the server, open the wiki folder in any Markdown editor — the knowledge is all there, human-readable, no proprietary format.
- **Cost-efficient at scale.** Two-step ingest with cached analysis means repeated ingest of similar sources costs near-zero tokens. Three cache layers stack for lint and query too.
- **Ingest is durable, not fragile.** Every ingest request becomes a queued job with automatic retry and a persistent audit record. Batch a hundred documents and resume after a crash — no work is lost.

---

## Architecture

```mermaid
flowchart TB
    subgraph ACCESS["  Access Layer  "]
        direction LR
        CLI["CLI\nsynthadoc …"]
        OBS["Obsidian Plugin"]
        MCP["Claude MCP\n⚠ optional"]
    end

    subgraph ENGINE["  Synthadoc Engine  ·  localhost:PORT  "]
        direction LR
        API["HTTP REST API"]
        QUEUE["Job Queue\nSQLite · asyncio · auto-retry"]
        API --> QUEUE
    end

    subgraph PROC["  Processing Agents  "]
        direction LR
        IA["IngestAgent\n+ SkillAgent\nPDF · URL · Web · Image · DOCX · …"]
        QA["QueryAgent\nBM25 + LLM synthesis"]
        LA["LintAgent\nContradiction · Orphan detection"]
    end

    subgraph OPS["  Admin & Ops  "]
        direction LR
        ADMIN["Health check · Install · Uninstall\nAudit · Cost report · Jobs monitor · Cache"]
    end

    subgraph PROV["  LLM Providers  "]
        LLM["Anthropic  ·  OpenAI  ·  Gemini  ·  Groq  ·  Ollama"]
    end

    subgraph STORE["  Storage  "]
        DB["wiki/*.md  ·  embeddings.db  ·  cache.db  ·  audit.db  ·  jobs.db"]
    end

    CLI -- HTTP --> API
    OBS -- HTTP --> API
    MCP -. "stdio MCP" .-> ENGINE

    QUEUE --> IA & QA & LA

    IA & QA & LA --> PROV
    IA & QA & LA --> STORE
    ADMIN -. "HTTP / direct" .-> STORE
```

For full architecture details, data models, API reference, and plugin development guide see **[docs/design.md](docs/design.md)**.

---

## What's Included in v0.1

- **3 agents** — IngestAgent (two-step cached synthesis), QueryAgent (BM25 + LLM), LintAgent (contradiction + orphan detection + auto-resolution)
- **7 built-in skills** — PDF, URL, Markdown/TXT, DOCX, XLSX/CSV, Image (vision), **Web search (Tavily — fully live)**
- **Folder-based skill system** — each skill is a self-contained folder with a `SKILL.md` manifest; intent-based dispatch alongside extension matching; drop a folder in `skills/` to add a new format without touching core code
- **3 access surfaces** — CLI (thin HTTP client), HTTP REST API, MCP server
- **Obsidian plugin** — ingest (with file picker when no note is active), query (responsive modal, stays open), lint report, jobs list — all from the command palette; ribbon shows engine health + page count
- **5 LLM providers** — Anthropic, OpenAI, **Gemini** (free tier), **Groq** (free tier), Ollama (local); switch with one config line
- **Two-step ingest** — `_analyse()` caches entity extraction + summary; decision prompt uses summary instead of full text; reduces cost on large documents
- **purpose.md scope filtering** — define what belongs in your wiki; the LLM skips out-of-scope sources cleanly
- **overview.md auto-summary** — 2-paragraph wiki overview regenerated automatically after every ingest that creates or updates pages
- **Audit CLI** — `synthadoc audit history / cost / events` query `audit.db` without needing direct access; `--analyse-only` flag previews ingest analysis before writing pages
- **3-layer cache** — embedding cache, LLM response cache, provider prompt cache
- **Cost guards** — configurable soft-warn and hard-gate USD thresholds
- **Hook system** — shell commands on `on_ingest_complete` and `on_lint_complete` lifecycle events; blocking or background; context passed as JSON on stdin; community hook library in [`hooks/`](hooks/)
- **Job queue** — SQLite-backed, persistent, retry with exponential backoff; non-retryable errors (`failed`) distinguished from exhausted-retry errors (`dead`)
- **Startup banner** — ASCII logo with version, port, wiki, and PID on `synthadoc serve`; plain-text version served at `GET /`
- **Multi-wiki** — unlimited isolated wikis, each on its own port
- **OpenTelemetry** — traces, metrics, structured logs; OTLP export optional
- **Cross-platform** — Windows, Linux, macOS

---

## Installation

### Prerequisites

- Python 3.11+
- An LLM API key — **Gemini Flash is free** (15 RPM / 1M tokens/day, no credit card): [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey). Alternatively: [Anthropic](https://console.anthropic.com/), [OpenAI](https://platform.openai.com/api-keys), [Groq](https://console.groq.com/keys) (free tier), or local [Ollama](https://ollama.com) (no key needed).

### Install Synthadoc

```bash
pip install synthadoc
```

### Set your API key

```bash
# macOS / Linux
export ANTHROPIC_API_KEY=sk-ant-…

# Windows (PowerShell)
$env:ANTHROPIC_API_KEY = "sk-ant-…"
```

To persist the key, add the export to your shell profile (`~/.bashrc`, `~/.zshrc`, or Windows user environment variables).

### Verify

```bash
synthadoc --version
```

---

## Quick-Start Guide

The fastest way to see Synthadoc in action is the **History of Computing** demo wiki. It includes 10 pre-built pages and four raw source files that demonstrate clean merge, contradiction, and orphan scenarios.

**Follow the full walkthrough: [docs/demo-guide.md](docs/demo-guide.md)**

The guide covers:
1. Installing the demo vault
2. Opening it in Obsidian
3. Installing the Obsidian and Dataview plugins
4. Running batch ingest
5. Resolving a contradiction (manual, LLM, and Claude MCP)
6. Fixing an orphan page
7. Controlling Synthadoc from Claude Desktop via MCP

---

## Configuration

### Global config — `~/.synthadoc/config.toml`

```toml
[agents]
default = { provider = "anthropic", model = "claude-opus-4-6" }
lint    = { model = "claude-haiku-4-5-20251001" }   # cheaper model for lint

[wikis]
research = "~/wikis/research"
work     = "~/wikis/work"
```

To switch to Gemini Flash (free tier):

```toml
[agents]
default = { provider = "gemini", model = "gemini-2.0-flash" }
```

### Per-project config — `<wiki-root>/.synthadoc/config.toml`

```toml
[server]
port = 7071          # each wiki needs its own port

[cost]
soft_warn_usd = 0.50
hard_gate_usd = 2.00

[ingest]
max_pages_per_ingest = 15

[web_search]
provider    = "tavily"
max_results = 20         # URLs fetched per query; each becomes an ingest job

[logs]
level        = "INFO"   # DEBUG | INFO | WARNING | ERROR
max_file_mb  = 5
backup_count = 5

[hooks]
on_ingest_complete = "python hooks/auto_commit.py"
```

Full config reference: [docs/design.md — Configuration](docs/design.md#configuration).

---

## Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# With coverage report
pytest --cov=synthadoc --cov-report=term-missing

# Run a specific test module
pytest tests/core/test_logging_config.py -v
```

The test suite covers: config loading, job queue, orchestrator, cost guard, cache, hooks, scheduler, HTTP API, MCP server, all agents, all skills, storage, search, CLI commands, and security/performance benchmarks.

---

## Command Reference by Use Case

### Setting up a wiki

```bash
# Create a new empty wiki
synthadoc install my-wiki --target ~/wikis/my-wiki

# Install the demo (includes pre-built pages and raw sources)
synthadoc install history --target ~/wikis/history --demo

# List available demo templates
synthadoc demo list
```

### Running the server

```bash
# Start HTTP API + MCP + job worker
synthadoc serve -w my-wiki

# Custom port
synthadoc serve -w my-wiki --port 7071

# Verbose debug logging to console
synthadoc serve -w my-wiki --verbose

# MCP-only (for Claude Desktop; no HTTP port bound)
synthadoc serve -w my-wiki --mcp-only
```

### Ingesting sources

```bash
# Single file or URL
synthadoc ingest report.pdf -w my-wiki
synthadoc ingest https://example.com/article -w my-wiki

# Entire folder (parallel, up to max_parallel_ingest at a time)
synthadoc ingest --batch raw_sources/ -w my-wiki

# Manifest file (one path or URL per line)
synthadoc ingest --batch --file sources.txt -w my-wiki

# Force re-ingest (bypass deduplication and cache)
synthadoc ingest --force report.pdf -w my-wiki
```

### Querying

```bash
# Ask a question — answer cites wiki pages
synthadoc query "What is Moore's Law?" -w my-wiki

# Save the answer as a new wiki page
synthadoc query "What is Moore's Law?" --save -w my-wiki
```

### Linting

```bash
# Run a full lint pass (enqueues job)
synthadoc lint run -w my-wiki

# Only contradictions
synthadoc lint run --scope contradictions -w my-wiki

# Only since a date
synthadoc lint run --since 2026-01-01 -w my-wiki

# Auto-apply high-confidence resolutions
synthadoc lint run --auto-resolve -w my-wiki

# Instant report (reads wiki files directly, no server needed)
synthadoc lint report -w my-wiki
```

### Monitoring jobs

```bash
# List all jobs (most recent first)
synthadoc jobs list -w my-wiki

# Filter by status
synthadoc jobs list --status pending -w my-wiki
synthadoc jobs list --status failed -w my-wiki
synthadoc jobs list --status dead -w my-wiki

# Single job detail
synthadoc jobs status <job-id> -w my-wiki

# Retry a dead job
synthadoc jobs retry <job-id> -w my-wiki

# Remove old records
synthadoc jobs purge --older-than 30 -w my-wiki
```

### Inspecting ingest results

```bash
# Preview how a source will be analysed without writing pages
synthadoc ingest report.pdf --analyse-only -w my-wiki
# → {"entities": [...], "tags": [...], "summary": "..."}
```

### Audit trail

```bash
# Last 20 ingest records (source, pages, tokens, cost)
synthadoc audit history -w my-wiki

# Token spend + cost for last 30 days (or --days N)
synthadoc audit cost -w my-wiki

# Audit events: contradictions found, auto-resolutions, cost gate triggers
synthadoc audit events -w my-wiki
```

### Searching without LLM

```bash
# BM25 keyword search — instant, zero tokens
synthadoc search "Turing machine" -w my-wiki
```

### Scheduling recurring jobs

```bash
# Register a nightly ingest
synthadoc schedule add --op "ingest --batch raw_sources/" --cron "0 2 * * *" -w my-wiki

# Weekly lint
synthadoc schedule add --op "lint" --cron "0 3 * * 0" -w my-wiki

# List scheduled jobs
synthadoc schedule list -w my-wiki

# Remove a scheduled job
synthadoc schedule remove <id> -w my-wiki
```

### Removing a wiki

```bash
# Two-step confirmation required — no --yes escape
synthadoc uninstall my-wiki
```

---

## Administrative Reference

### Health and status

```bash
# Wiki statistics: pages, queue depth, spend, cache hit rate
synthadoc status -w my-wiki

# Liveness probe (useful in scripts and monitoring)
curl http://127.0.0.1:7070/health
```

Expected `status` output:
```
Wiki: my-wiki  |  Pages: 34  |  Sources: 12
Last ingest: 4 min ago (report.pdf)
Queue: 0 jobs pending  |  Dead jobs: 1
Token spend (30d): $1.84  |  Cache savings: $0.72 (28%)
Contradictions: 2 unresolved  |  Orphan pages: 1
```

### Logs

Synthadoc writes three log artefacts per wiki:

| File | Location | Format | Use |
|------|----------|--------|-----|
| `log.md` | `<wiki-root>/log.md` | Human-readable Markdown | Read inside Obsidian; shows every ingest, contradiction, lint event |
| `synthadoc.log` | `<wiki-root>/.synthadoc/logs/` | JSON lines (rotating) | Structured debug/ops log; grep or pipe to jq |
| `audit.db` | `<wiki-root>/.synthadoc/audit.db` | SQLite (append-only) | Source hashes, cost records, job history |

**Tailing the JSON log:**

```bash
# Tail and pretty-print with jq
tail -f .synthadoc/logs/synthadoc.log | jq .

# Filter to errors only
tail -f .synthadoc/logs/synthadoc.log | jq 'select(.level == "ERROR")'

# Filter to a specific job
tail -f .synthadoc/logs/synthadoc.log | jq 'select(.job_id == "abc123")'
```

**Log rotation:** When `synthadoc.log` reaches `max_file_mb`, it is renamed to `synthadoc.log.1`; the previous `.1` becomes `.2`; files beyond `backup_count` are deleted. Total disk ≈ `max_file_mb × (backup_count + 1)`.

**Changing log level at runtime:** Edit `[logs] level` in `.synthadoc/config.toml` and restart `synthadoc serve`. Or pass `--verbose` to get `DEBUG` for one session without editing config.

### Audit trail

```bash
# Ingest history (no sqlite3 needed)
synthadoc audit history -w my-wiki          # last 20 records
synthadoc audit cost -w my-wiki             # spend summary, last 30 days
synthadoc audit cost --days 7 -w my-wiki    # weekly view
synthadoc audit events -w my-wiki           # contradictions, resolutions, cost gates

# Direct sqlite3 queries for custom analysis
sqlite3 .synthadoc/audit.db \
  "SELECT source, hash, cost_usd, ingested_at FROM ingest_log ORDER BY ingested_at DESC LIMIT 20"
sqlite3 .synthadoc/audit.db \
  "SELECT SUM(cost_usd) FROM ingest_log"
```

### Cache management

```bash
# Show cache stats (in status output)
synthadoc status -w my-wiki

# Wipe all LLM response cache entries
synthadoc cache clear -w my-wiki
```

Cache invalidation happens automatically when:
- A source file's SHA-256 hash changes (content changed)
- `CACHE_VERSION` is bumped in `core/cache.py` (after prompt template edits)
- `--force` is passed to ingest

### OpenTelemetry integration

By default, traces and metrics are written to `<wiki-root>/.synthadoc/logs/traces.jsonl`. To send to any OTLP backend (Jaeger, Grafana Tempo, Honeycomb, Datadog):

```toml
# ~/.synthadoc/config.toml
[observability]
exporter      = "otlp"
otlp_endpoint = "http://localhost:4317"
```

### Debugging

```bash
# Start server with DEBUG console logging
synthadoc serve -w my-wiki --verbose

# Check for configuration problems
synthadoc status -w my-wiki     # prints pre-flight warnings

# View recent job failures
synthadoc jobs list --status failed -w my-wiki
synthadoc jobs status <job-id> -w my-wiki    # shows error message + traceback

# Force a re-ingest to rule out cache issues
synthadoc ingest --force problem.pdf -w my-wiki
```

---

## Understanding Logs and the Audit Trail

### `log.md` — the human log

Every significant event is appended as a Markdown entry:

```markdown
## 2026-04-10 14:32 — Ingest: constitutional-ai.pdf
- Pages created: `constitutional-ai`
- Pages updated: `ai-alignment-overview`
- Pages flagged (contradiction): `reward-hacking` ⚠
- Tokens: 4,820  |  Cost: $0.031  |  Cache hits: 3
```

Open `log.md` in Obsidian to browse and search the full history.

### `synthadoc.log` — the structured log

JSON lines format. Each record:

```json
{
  "ts": "2026-04-10T14:32:01",
  "level": "INFO",
  "logger": "synthadoc.agents.ingest_agent",
  "msg": "Page created: alan-turing",
  "job_id": "abc123",
  "operation": "ingest",
  "wiki": "history-of-computing"
}
```

Standard fields: `ts`, `level`, `logger`, `msg`. Job-scoped fields (added by `get_job_logger`): `job_id`, `operation`, `wiki`. Future: `trace_id` for OTel correlation.

Log levels follow RFC 5424:

| Level | Used for |
|-------|----------|
| DEBUG | LLM prompt/response bodies, cache keys, BM25 scores |
| INFO  | Job start/complete, page created/updated, server started |
| WARNING | Soft failures (network unreachable), cache miss spikes |
| ERROR | Job failed, LLM API error, file write failed |
| CRITICAL | Server cannot start (port conflict, missing key, bad wiki root) |

### `audit.db` — the immutable record

SQLite, append-only. Records: every ingest (source path, SHA-256, cost, timestamp), every cost threshold crossing, every auto-resolution applied, every job that died. Never modified; only `jobs purge` deletes records older than a threshold.

---

## Customization

### Adding a custom skill (new file format)

1. Create `<wiki-root>/skills/my_format.py` (or `~/.synthadoc/skills/` for global availability).
2. Subclass `BaseSkill` (Apache-2.0 licensed — no AGPL obligation on your skill):

```python
# SPDX-License-Identifier: MIT   ← any licence you like
from synthadoc.skills.base import BaseSkill, ExtractedContent, SkillMeta

class NotionSkill(BaseSkill):
    @classmethod
    def meta(cls) -> SkillMeta:
        return SkillMeta(
            name="notion",
            description="Extracts text from Notion export ZIP files",
            extensions=[".notion.zip"],
        )

    def extract(self, source: str) -> ExtractedContent:
        # … your extraction logic …
        return ExtractedContent(title="My Page", body="extracted text …")
```

3. Drop the file in the skills directory. Synthadoc hot-loads it on the next ingest — no restart needed.

To bundle resource files (prompt templates, lookup tables):

```
skills/
  my_format.py
  my_format/
    resources/
      extract_prompt.md
```

Access them inside your skill with `self.get_resource("extract_prompt.md")`.

### Adding a custom LLM provider

Subclass `LLMProvider` from `synthadoc/providers/base.py` (also Apache-2.0):

```python
from synthadoc.providers.base import LLMProvider, Message, CompletionResponse

class MyProvider(LLMProvider):
    async def complete(self, messages: list[Message], **kwargs) -> CompletionResponse:
        …
```

Place in `~/.synthadoc/providers/` or the wiki `providers/` directory.

### Writing hooks

Hooks are shell commands (any language) that receive a JSON context on stdin:

```python
# hooks/auto_commit.py
import json, subprocess, sys
ctx = json.load(sys.stdin)
if ctx["pages_created"] or ctx["pages_updated"]:
    subprocess.run(["git", "add", "-A"], cwd=ctx["wiki_root"])
    subprocess.run(["git", "commit", "-m", f"ingest: {ctx['source']}"],
                   cwd=ctx["wiki_root"])
```

Register in `.synthadoc/config.toml`:

```toml
[hooks]
on_ingest_complete = "python hooks/auto_commit.py"
```

Available events: `on_ingest_complete`, `on_ingest_failed`, `on_contradiction_found`, `on_lint_complete`, `on_query_saved`, `on_batch_complete`, `on_cost_warning`, `on_dead_job`.

Set `blocking = true` to make the hook gate the operation:

```toml
on_contradiction_found = { cmd = "python hooks/notify.py", blocking = true }
```

### Cache invalidation control

| Scenario | Action |
|----------|--------|
| Source file changed | Automatic — SHA-256 changes, cache miss on next ingest |
| Prompt template edited | Bump `CACHE_VERSION` in `synthadoc/core/cache.py` |
| Force fresh LLM call | `synthadoc ingest --force <source> -w my-wiki` |
| Wipe all cached responses | `synthadoc cache clear -w my-wiki` |

### Per-wiki AGENTS.md

Edit `<wiki-root>/AGENTS.md` to give the LLM domain-specific instructions — what to emphasize, how to name pages, what to cross-reference. This is the highest-priority instruction source for every agent run against this wiki.

---

## What's Coming in v0.2

Target: week of 2026-04-25.

| Feature | Notes |
|---------|-------|
| **Web UI** | Browser-based dashboard — view pages, run jobs, inspect contradictions and orphans without Obsidian |
| **Vector search + re-ranking** | Hybrid BM25 + `fastembed` local vectors; better recall on semantically related queries |
| **Graph-aware retrieval** | Multi-hop wikilink traversal for queries like "What connects Turing to von Neumann?" |
| **Larger corpus support** | Sharded index, incremental embedding updates, streaming ingest for very large documents |
| **Obsidian plugin: web search modal** | Full UI for `search for:` intent queries — type a topic, watch pages appear live |
| **Mistral + Bedrock providers** | Additional OpenAI-compatible and AWS-native LLM backends |

---

## Licensing

| Component | Licence |
|-----------|---------|
| Core server and all other source files | [AGPL-3.0-or-later](LICENSE) |
| `synthadoc/skills/base.py` | Apache-2.0 — extend freely, any licence |
| `synthadoc/providers/base.py` | Apache-2.0 — extend freely, any licence |

Copyright (C) 2026 Paul Chen / axoviq.com

Contributions require signing a CLA before a PR can be merged. See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Links

- Design document: [docs/design.md](docs/design.md)
- Demo walkthrough: [docs/demo-guide.md](docs/demo-guide.md)
- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md)
- Issues: [GitHub Issues](../../issues)
