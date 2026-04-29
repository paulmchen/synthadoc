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

       S Y N T H A D O C
    Community Edition  v0.2.0
  ────────────────────────────────
  Domain-agnostic LLM wiki engine
```

[![CI](https://github.com/axoviq-ai/synthadoc/actions/workflows/ci.yml/badge.svg)](https://github.com/axoviq-ai/synthadoc/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Faxoviq-ai%2Fsynthadoc%2Fmain%2Fdocs%2Fbadges.json&query=%24.coverage&label=Coverage&suffix=%25&color=brightgreen)](https://github.com/axoviq-ai/synthadoc/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](https://github.com/axoviq-ai/synthadoc/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-yellow.svg)](https://www.python.org/)
[![Skills](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Faxoviq-ai%2Fsynthadoc%2Fmain%2Fdocs%2Fbadges.json&query=%24.skills&label=Skills&color=purple)](https://github.com/axoviq-ai/synthadoc/tree/main/synthadoc/skills)
[![CLI](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Faxoviq-ai%2Fsynthadoc%2Fmain%2Fdocs%2Fbadges.json&query=%24.cli_commands&label=CLI%20commands&color=darkblue)](https://github.com/axoviq-ai/synthadoc)
[![Obsidian](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Faxoviq-ai%2Fsynthadoc%2Fmain%2Fdocs%2Fbadges.json&query=%24.obsidian_commands&label=Obsidian%20commands&color=blueviolet)](https://github.com/axoviq-ai/synthadoc/tree/main/obsidian-plugin)
[![Version](https://img.shields.io/badge/Community%20Edition-v0.2.0-orange.svg)](https://github.com/axoviq-ai/synthadoc)

**Document version: v0.2.0**

**Engineered for solo users and enterprises alike, providing a domain-specific knowledge base that scales seamlessly while maintaining accuracy through autonomous self-optimization.**

> Built for individuals, small teams, and large organizations who need a knowledge base that stays accurate as documents accumulate.

Synthadoc reads your raw source documents — PDFs, spreadsheets, PPTs, web pages, images, Word files, TXTs — and uses an LLM to synthesize them into a persistent, structured wiki. Cross-references are built automatically, contradictions are detected and surfaced, orphan pages are flagged, and every answer cites its sources. Outputs are stored as local Markdown files, ensuring seamless integration and autonomous management within [Obsidian](https://obsidian.md) or any wiki-compliant ecosystem.

---

## Who Is It For?

Synthadoc scales from a single researcher to a company-wide knowledge platform:


| Team size               | Typical use case                                                                                                                                                                                                                                                                                    |
| ----------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Solo / 1–2 people**  | Personal research wiki, freelance knowledge base, indie hacker documentation - run it free on Gemini Flash or a local Ollama model with zero ongoing cost                                                                                                                                           |
| **Small team (3–20)**  | Centralized internal knowledge base for startups and departments that aggregates diverse individual data sources into a unified, high-integrity wiki. The system automatically resolves contradictions and scales autonomously, ensuring organizational intelligence grows in tandem with your team |
| **Medium / enterprise** | Compliance-sensitive knowledge bases that must stay local; per-department wikis on separate ports; audit trail for every ingest and cost event; hook system for CI/CD integration; OpenTelemetry for ops dashboards                                                                                 |

No cloud account. No vendor lock-in. The wiki is plain Markdown — open it in any editor, back it up with git, sync it with any cloud drive.

---

## Inspiration and Vision

> *"The LLM should be able to maintain a wiki for you."*
> — Andrej Karpathy, [LLM Wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)

Most knowledge-management tools retrieve and summarize at query time. Synthadoc inverts this: it **compiles knowledge at ingest time**. Every new source enriches and cross-links the entire corpus, not just appends a new chunk. The wiki is the artifact — readable, editable, and browsable without any tool running.

**Long-term alignment:**


| Direction                | How Synthadoc moves there                                                                                                                                                                                     |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Agent orchestration      | Orchestrator dispatches parallel IngestAgent, QueryAgent, LintAgent sub-agents with cost guards and retry backoff                                                                                             |
| Sub-agent skills/plugins | Featuring a 3-tier lazy-load capability system, the platform allows for the injection of custom skills and hooks via a plug-and-play interface, ensuring core stability is never compromised during extension |
| LLM wiki vs. RAG         | Pre-compiled structured knowledge beats query-time synthesis for contradiction detection, graph traversal, and offline access                                                                                 |
| CLI / HTTP               | A unified interface via CLI and RESTful endpoints, the system streamlines full-spectrum integration: from data ingestion and querying to automated linting, security auditing, and job orchestration          |
| Local-first              | All data stays on your machine; localhost-only network binding; no cloud dependency except the LLM API itself                                                                                                 |
| Provider choice          | LLM backends including free-tier Gemini and Groq, plus DeepSeek and MiniMax for cheapest paid text rates — no single-vendor dependency                                                                                    |

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

### 6. Wiki structure decays as content grows; Synthadoc regenerates it

As the wiki accumulates pages the `index.md` table of contents, domain scope (`purpose.md`), and LLM behaviour guidelines (`AGENTS.md`) can drift out of sync with actual content. The `scaffold` command re-generates all three from the current wiki state using the LLM — creating category-aware index entries, refreshed scope boundaries, and updated terminology guidelines — without touching pages already linked in the index. Run it once after initial install to get a rich scaffold, then schedule it weekly as the wiki grows.

### Business values


| Value                 | How                                                                                 |
| --------------------- | ----------------------------------------------------------------------------------- |
| **Faster onboarding** | New team members query the wiki instead of digging through documents                |
| **Audit trail**       | Every ingest recorded in`audit.db` with source hash, token count, and timestamp     |
| **Cost control**      | Configurable soft-warn and hard-gate thresholds; 3-layer cache reduces repeat spend |
| **Compliance**        | Local-first — source documents and compiled knowledge never leave your machine     |
| **Extensibility**     | Hooks fire on every event; custom skills load without a server restart              |

---

## Why Synthadoc?

### Competitive advantages


| Capability                   | Synthadoc                                                      | Typical RAG | NotebookLM | Notion AI |
| ---------------------------- | -------------------------------------------------------------- | ----------- | ---------- | --------- |
| Ingest-time synthesis        | **Yes**                                                        | No          | Partial    | No        |
| Contradiction detection      | **Yes**                                                        | No          | No         | No        |
| Orphan page detection        | **Yes**                                                        | No          | No         | No        |
| Persistent wikilink graph    | **Yes**                                                        | No          | No         | No        |
| Local-first (no cloud data)  | **Yes**                                                        | Varies      | No         | No        |
| Custom skill plugins         | **Yes**                                                        | Limited     | No         | No        |
| Obsidian integration         | **Yes**                                                        | No          | No         | No        |
| Cost guard + audit trail     | **Yes**                                                        | No          | No         | No        |
| Hook / CI integration        | **Yes** (2 events)                                             | No          | No         | No        |
| Offline browsable artifact   | **Yes**                                                        | No          | No         | No        |
| Multi-wiki isolation         | **Yes**                                                        | No          | No         | No        |
| Web search → wiki pages     | **Yes**                                                        | No          | No         | No        |
| Multiple LLMs support       | **Yes** (Gemini, Groq, MiniMax, DeepSeek, Anthropic, OpenAI, Ollama) | No          | No         | No        |
| Auto wiki overview page      | **Yes**                                                        | No          | No         | No        |
| Resumable job queue + retry  | **Yes**                                                        | No          | No         | No        |
| Query decomposition          | **Yes** (parallel sub-queries)                                 | No          | No         | No        |
| Knowledge gap detection      | **Yes**                                                        | No          | No         | No        |
| Web search decomposition     | **Yes** (parallel Tavily)                                      | No          | No         | No        |
| Semantic re-ranking (vector) | **Yes** (optional fastembed)                                   | Varies      | No         | No        |
| Scaffold automation          | **Yes**                                                        | No          | No         | No        |

### Key differentiators vs. RAG

RAG chunks documents and retrieves them at query time. Synthadoc **compiles** knowledge: every new source is synthesized into the existing wiki graph at ingest time.

- **Contradictions are caught, not blended.** When two sources disagree, Synthadoc flags the page — RAG silently averages both claims.
- **Knowledge is linked, not scattered.** `[[wikilinks]]` connect related pages into a navigable graph visible in Obsidian and queryable with Dataview.
- **The artifact outlives the tool.** Close the server, open the wiki folder in any Markdown editor — the knowledge is all there, human-readable, no proprietary format.
- **Cost-efficient at scale.** Two-step ingest with cached analysis means repeated ingest of similar sources costs near-zero tokens. Three cache layers stack for lint and query too.
- **Ingest is durable, not fragile.** Every ingest request becomes a queued job with automatic retry and a persistent audit record. Batch a hundred documents and resume after a crash — no work is lost.

---

## Architecture

![Synthadoc Architecture](docs/png/architecture.png)

For full architecture details, data models, API reference, and plugin development guide see **[docs/design.md](docs/design.md)**.

---

## What's Included

See [docs/design.md — Appendix A: Release Feature Index](docs/design.md#appendix-a--release-feature-index) for a full feature list by version.

---

## Installation

### Prerequisites


| Requirement    | Version | Notes                               |
| -------------- | ------- | ----------------------------------- |
| Python         | 3.11+   |                                     |
| Node.js        | 18+     | Obsidian plugin build only          |
| Git            | any     |                                     |
| LLM API key    | —      | At least one required (see below)   |
| Tavily API key | —      | Optional — web search feature only |

**LLM API key — at least one required:**


| Provider         | Free tier                                     | Vision          | Get key                                                       |
| ---------------- | --------------------------------------------- | --------------- | ------------------------------------------------------------- |
| **Gemini Flash** | Yes — 15 RPM / 1M tokens/day, no credit card | Yes             | [aistudio.google.com](https://aistudio.google.com/app/apikey) |
| Groq             | Yes — rate-limited                           | No              | [console.groq.com](https://console.groq.com/keys)             |
| Ollama           | Yes — runs locally, no key                   | Model-dependent | [ollama.com](https://ollama.com)                              |
| MiniMax          | No — pay-per-token                           | Yes             | [platform.minimax.io](https://platform.minimax.io/)           |
| DeepSeek         | No — pay-per-token (very cheap text rates)   | No              | [platform.deepseek.com](https://platform.deepseek.com/api_keys) |
| Anthropic        | No                                            | Yes             | [console.anthropic.com](https://console.anthropic.com/)       |
| OpenAI           | No                                            | Yes             | [platform.openai.com](https://platform.openai.com/api-keys)   |

**Tavily API key (optional — enables web search):**
Get a free key at [tavily.com](https://tavily.com). Without it, web search jobs will fail but all other features work normally.

---

### Step 1 — Clone and install

```bash
git clone https://github.com/paulmchen/synthadoc.git
cd synthadoc
pip3 install -e ".[dev]"
```

### Step 2 — Run the Python test suite

Validate that the Python engine builds and all tests pass before proceeding:

```bash
pytest --ignore=tests/performance/ -q
```

Expected: all tests pass, 0 failures. If any fail, check the error output before continuing.

Performance benchmarks (optional — Linux/macOS, measures SLOs):

```bash
pytest tests/performance/ -v --benchmark-disable
```

### Step 3 — Build and test the Obsidian plugin

```bash
cd obsidian-plugin
npm install
npm run build    # produces main.js
npm test         # runs Vitest unit tests
```

### Step 4 — Set your API keys

**At least one LLM API key is required** — Synthadoc will not start without one.

Synthadoc defaults to **Gemini Flash** as the LLM provider — it's free, requires no
credit card, and offers 1 million tokens per day. Get a key at
**aistudio.google.com/app/apikey** (click "Create API key").

Web search uses **Tavily** (`TAVILY_API_KEY`) — optional, only needed for
`synthadoc ingest "search for: …"` jobs.

```bash
# macOS / Linux — add to ~/.bashrc or ~/.zshrc to persist
export GEMINI_API_KEY=AIza…          # default — free tier, 1M tokens/day
export GROQ_API_KEY=gsk_…            # alternative free tier — 100K tokens/day
export ANTHROPIC_API_KEY=sk-ant-…    # paid — highest quality
export MINIMAX_API_KEY=…             # paid — text rates (image support)
export DEEPSEEK_API_KEY=…            # paid — text rates (no image support)
export TAVILY_API_KEY=tvly-…         # web search (optional)

# Windows cmd — current session only
set GEMINI_API_KEY=AIza…
set GROQ_API_KEY=gsk_…
set ANTHROPIC_API_KEY=sk-ant-…
set MINIMAX_API_KEY=…
set DEEPSEEK_API_KEY=…
set TAVILY_API_KEY=tvly-…

# Windows cmd — permanent (open a new cmd window after running)
setx GEMINI_API_KEY AIza…
setx GROQ_API_KEY gsk_…
setx ANTHROPIC_API_KEY sk-ant-…
setx MINIMAX_API_KEY …
setx DEEPSEEK_API_KEY sk-…
setx TAVILY_API_KEY tvly-…
```

To switch provider, edit `[agents]` in `<wiki-root>/.synthadoc/config.toml` and restart
`synthadoc serve`. See [Appendix — Switching LLM providers](docs/user-quick-start-guide.md#appendix-c--switching-llm-providers) for step-by-step instructions.

### Step 5 — Verify

```bash
synthadoc --version
```

### Step 6 — Install a demo wiki, then start the engine

A **wiki** is a self-contained, structured knowledge base — a folder of Markdown pages linked by topic, maintained and cross-referenced automatically by Synthadoc. Think of it as a living document that grows smarter with every source you feed it: each ingest pass adds new pages, updates existing ones, and flags contradictions. For your own work, you can build and grow a domain-specific wiki — whether that's market research, a technical knowledge base, or a team handbook — and query it in plain English or other languages at any time.

A wiki must be installed before the engine can serve it. The fastest way to get started is the **History of Computing** demo, which ships with 10 pre-built pages and sample source files — no LLM API key required to browse it.

**Install the demo wiki:**

```bash
# Linux / macOS
synthadoc install history-of-computing --target ~/wikis --demo

# Windows (cmd.exe)
synthadoc install history-of-computing --target %USERPROFILE%\wikis --demo
```

**Then start the engine:**

```bash
# Foreground — keeps the terminal; logs stream to the console
synthadoc serve -w history-of-computing

# Background — releases the terminal; logs go to the wiki log file
synthadoc serve -w history-of-computing --background
```

The server binds to `http://127.0.0.1:7070` by default (port is set in `<wiki-root>/.synthadoc/config.toml`). Leave it running while you work — the Obsidian plugin, CLI ingest commands, and query commands all talk to it.

To stop a background server:

```bash
# Linux / macOS
kill <PID>

# Windows (cmd)
taskkill /PID <PID> /F
```

The PID is printed when the background server starts and saved to `<wiki-root>/.synthadoc/server.pid`.

---

## Quick-Start Guide

The **History of Computing** demo includes 13 pre-built pages, raw source files covering clean-merge, contradiction, and orphan scenarios, and a full walkthrough of key Synthadoc feature.

**Full step-by-step walkthrough: [docs/user-quick-start-guide.md](docs/user-quick-start-guide.md)**

The guide covers:

1. Verify the demo server started (banner, health check)
2. Install Dataview in Obsidian
3. Install the Synthadoc plugin and open the vault
4. Review wiki structure and key files (index, purpose, AGENTS.md, dashboard)
5. Query the pre-built wiki — including knowledge gap detection
6. Batch ingest all demo source files
7. Resolve a contradiction
8. Fix an orphan page
9. Web search ingestion with automatic decomposition
10. Enrich the wiki with scaffold (regenerate/update index, purpose, AGENTS.md)
11. Audit features (token cost, history, events)
12. Schedule recurring operations

---

## Creating Your Own Wiki

Unlike the demo (which ships with pre-built pages), your own wiki starts from a domain description and grows as you feed it sources. Three commands are all you need to get started:

```bash
synthadoc install market-condition-canada --target ~/wikis --domain "Market conditions and trends in Canada"
synthadoc use market-condition-canada   # set as the default wiki — no -w needed from here on
synthadoc serve
```

`--domain` is a free-text description of the subject area — the LLM uses it to generate four domain-aware starter files via scaffold:


| File                | Purpose                                                                     |
| ------------------- | --------------------------------------------------------------------------- |
| `wiki/index.md`     | Table of contents — domain-relevant categories with`[[wikilinks]]`         |
| `wiki/purpose.md`   | Scope declaration — tells the ingest agent what belongs and what to ignore |
| `AGENTS.md`         | LLM behaviour guidelines — tone, terminology, and synthesis style          |
| `wiki/dashboard.md` | Live Dataview dashboard — orphan pages, contradictions, page count         |

Open the wiki folder in Obsidian as a new vault and install both the Dataview and Synthadoc plugins (required once per wiki). The Quick-Start Guide covers this setup in detail — see [docs/user-quick-start-guide.md](docs/user-quick-start-guide.md).

**Recommended growth loop:**

**1. Seed with web searches** — pull in real content for the topics you care about:

```bash
synthadoc ingest "search for: Economy, employment and labour market analysis in Toronto GTA"
synthadoc ingest "search for: Bank of Canada interest rate outlook 2025"
synthadoc jobs list   # watch progress
```

Each search fans out into up to 20 parallel URL ingest jobs. Query decomposition and web search decomposition (see below) make broad topics yield much richer results than a single search.

**2. Lint and query** — check for contradictions and verify the wiki answers your questions:

```bash
synthadoc lint run
synthadoc lint report
synthadoc query "What are the current employment trends in the Toronto GTA?"
```

**3. Re-run scaffold** — after pages accumulate, scaffold regenerates a richer index that reflects actual content. Pages already linked in `index.md` are never overwritten:

```bash
synthadoc scaffold
```

**4. Schedule recurring updates** — keep the wiki fresh automatically:

```bash
synthadoc schedule add --op "ingest" --source "search for: Toronto GTA economic indicators latest" --cron "0 2 * * *"
synthadoc schedule add --op "scaffold" --cron "0 4 * * 0"
```

### How decomposition works

Both `query` and web search `ingest` automatically split complex inputs into focused parallel sub-tasks — a compound question becomes multiple BM25 retrievals merged before synthesis; a broad search topic becomes multiple focused Tavily keyword searches whose results are merged and deduplicated. Both fall back gracefully if the LLM decomposition call fails.

See [docs/design.md — Query decomposition and web search decomposition](docs/design.md#query-decomposition) for the full design.

### Semantic re-ranking (vector search)

BM25 keyword search is the default. Optional vector re-ranking (`BAAI/bge-small-en-v1.5` cosine similarity) improves recall on conceptually related queries — enable it by installing `fastembed` and setting `[search] vector = true` in config. The ~130 MB model is downloaded once; BM25 stays active as fallback.

See [docs/design.md — Semantic re-ranking](docs/design.md#semantic-re-ranking) for configuration options and performance notes.

### Knowledge gap workflow

When a query returns thin or empty results, the wiki doesn't yet cover the topic. Fill the gap with a targeted web search ingest, wait for jobs, then re-query. Each ingest cycle makes the wiki denser — future queries need the web less.

See [docs/design.md — Knowledge gap workflow](docs/design.md#knowledge-gap-workflow) for the full pattern.

See [docs/design.md](docs/design.md) for a full description of how ingest, contradiction detection, and orphan tracking work under the hood.

---

## Configuration

You do not need to configure anything to run the demo. The demo wiki ships with its own settings and sensible built-in defaults cover everything else. Set your API key env var, run `synthadoc serve`, and go.

For the full configuration reference — layer precedence, global vs. per-project config, all keys and defaults — see [Appendix E — Configuration](docs/user-quick-start-guide.md#appendix-e--configuration) in the Quick-Start Guide, or [docs/design.md — Configuration](docs/design.md#configuration) for the complete technical reference.

---

## Command Reference by Use Case

### Setting up a wiki

```bash
# Create a new empty wiki (LLM scaffold runs automatically if API key is set)
synthadoc install my-wiki --target ~/wikis --domain "Machine Learning"

# Create a wiki on a specific port (useful when running multiple wikis)
synthadoc install my-wiki --target ~/wikis --domain "Machine Learning" --port 7071

# Install the demo (includes pre-built pages and raw sources — no LLM call needed)
synthadoc install history-of-computing --target ~/wikis --demo

# List available demo templates
synthadoc demo list
```

### Refreshing wiki scaffold

After install, you can re-run the LLM scaffold at any time to regenerate domain-specific content (index categories, AGENTS.md guidelines, purpose.md scope). Pages already linked in `index.md` are protected and preserved.

```bash
# Regenerate scaffold for an existing wiki
synthadoc scaffold -w my-wiki

# Schedule weekly refresh (runs every Sunday at 4 AM)
synthadoc schedule add --op "scaffold" --cron "0 4 * * 0" -w my-wiki
```

`config.toml` and `dashboard.md` are never modified by `scaffold`.

### Running the server

```bash
# Start HTTP API + job worker (foreground — terminal stays attached)
synthadoc serve -w my-wiki

# Detach to background — banner shown, then shell is released
# All logs go to <wiki>/.synthadoc/logs/synthadoc.log
synthadoc serve -w my-wiki --background

# Custom port
synthadoc serve -w my-wiki --port 7071

# Verbose debug logging to console
synthadoc serve -w my-wiki --verbose
```

### Ingesting sources

```bash
# Single file or URL
synthadoc ingest report.pdf -w my-wiki
synthadoc ingest https://example.com/article -w my-wiki

# Entire folder (parallel, up to max_parallel_ingest at a time)
synthadoc ingest --batch raw_sources/ -w my-wiki

# Manifest file — ingest a curated list of sources in one shot.
# sources.txt: one entry per line; each line is either an absolute file path
# (PDF, DOCX, PPTX, MD, …) or a URL. Blank lines and # comments are ignored.
# Each entry becomes a separate job in the queue, processed sequentially.
#
# Example sources.txt:
#   /home/user/docs/research-paper.pdf
#   /home/user/slides/keynote.pptx
#   https://en.wikipedia.org/wiki/Alan_Turing
#   # this line is ignored
synthadoc ingest --file sources.txt -w my-wiki

# Force re-ingest (bypass deduplication and cache)
synthadoc ingest --force report.pdf -w my-wiki

# Web search — triggers a Tavily search, then ingests each result URL as a child job.
# Prefix the query with any recognised intent: "search for:", "find on the web:",
# "look up:", or "web search:"  (prefix is stripped before the search is sent)
# Requires TAVILY_API_KEY to be set.
#
# Note: web search content is NOT saved to raw_sources/. The flow is direct:
#   query → Tavily → URLs → each URL fetched → wiki pages written
# raw_sources/ is for user-provided local files (PDF, DOCX, PPTX, etc.) only.
# The wiki pages themselves are the persistent output of a web search.
synthadoc ingest "search for: Bank of Canada interest rate decisions 2024" -w my-wiki
synthadoc ingest "find on the web: unemployment trends Ontario Q1 2025" -w my-wiki

# Limit how many URLs are enqueued (default 20, overrides [web_search] max_results)
synthadoc ingest "search for: quantum computing basics" --max-results 5 -w my-wiki

# Multiple web searches at once via a manifest file
# web-searches.txt:
#   search for: Bank of Canada interest rate decisions 2024
#   find on the web: unemployment trends Ontario Q1 2025
#   look up: Toronto housing market affordability index
synthadoc ingest --file web-searches.txt -w my-wiki
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

# Cancel all pending jobs at once (e.g. after a bad batch ingest)
synthadoc jobs cancel -w my-wiki        # prompts for confirmation
synthadoc jobs cancel --yes -w my-wiki  # skip confirmation

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
# Ingest history: timestamp, source file, wiki page, tokens, cost
synthadoc audit history -w my-wiki            # last 50 records
synthadoc audit history -n 100 -w my-wiki     # last 100 records
synthadoc audit history --json -w my-wiki     # raw JSON for scripting

# Token usage: totals + daily breakdown (cost always $0.0000 in v0.1)
synthadoc audit cost -w my-wiki               # last 30 days
synthadoc audit cost --days 7 -w my-wiki      # last 7 days

# Audit events: contradictions found, auto-resolutions, cost gate triggers
synthadoc audit events -w my-wiki             # last 100 events
synthadoc audit events --json -w my-wiki      # raw JSON for scripting
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

Stop the server for that wiki before uninstalling — the serve process must not be running
when the directory is deleted.

```bash
# Stop the background server (PID is in <wiki-root>/.synthadoc/server.pid)
kill $(cat ~/wikis/my-wiki/.synthadoc/server.pid)          # Linux / macOS
taskkill /PID <pid> /F                                      # Windows

# Then uninstall — two-step confirmation required, no --yes escape
synthadoc uninstall my-wiki
```

For Obsidian plugin commands see [Appendix A — Obsidian Plugin Command Reference](docs/user-quick-start-guide.md#appendix-a--obsidian-plugin-commands) in the Quick-Start Guide.

---

## Administrative Reference

### Health and status

```bash
# Wiki statistics: pages, queue depth, cache hit rate
synthadoc status -w my-wiki

# Liveness probe (useful in scripts and monitoring)
# Port is per-wiki — check [server] port in <wiki-root>/.synthadoc/config.toml
# Default is 7070; each additional wiki uses its own port (7071, 7072, …)
curl http://127.0.0.1:7070/health
```

Expected `status` output:

```
Wiki:         /home/user/wikis/my-wiki
Pages:        34
Jobs pending: 0
Jobs total:   12
```

### Logs

Synthadoc writes three log artefacts per wiki:


| File            | Location                          | Format                  | Use                                                                 |
| --------------- | --------------------------------- | ----------------------- | ------------------------------------------------------------------- |
| `log.md`        | `<wiki-root>/log.md`              | Human-readable Markdown | Read inside Obsidian; shows every ingest, contradiction, lint event |
| `synthadoc.log` | `<wiki-root>/.synthadoc/logs/`    | JSON lines (rotating)   | Structured debug/ops log; grep or pipe to jq                        |
| `audit.db`      | `<wiki-root>/.synthadoc/audit.db` | SQLite (append-only)    | Source hashes, cost records, job history                            |

**Tailing the JSON log:**

```bash
# Tail and pretty-print with jq
tail -f .synthadoc/logs/synthadoc.log | jq .

# Filter to errors only
tail -f .synthadoc/logs/synthadoc.log | jq 'select(.level == "ERROR")'

# Filter to a specific job
# job_id is present only on records logged in job context (ingest/lint workers)
tail -f .synthadoc/logs/synthadoc.log | jq 'select(.job_id == "abc123")'
```

**Log rotation:** When `synthadoc.log` reaches `max_file_mb`, it is renamed to `synthadoc.log.1`; the previous `.1` becomes `.2`; files beyond `backup_count` are deleted. Total disk ≈ `max_file_mb × (backup_count + 1)`.

**Changing log level at runtime:** Edit `[logs] level` in `.synthadoc/config.toml` and restart `synthadoc serve`. Or pass `--verbose` to get `DEBUG` for one session without editing config.

### Audit trail

```bash
synthadoc audit history -w my-wiki          # table: timestamp, source file, wiki page, tokens, cost
synthadoc audit history -n 100 -w my-wiki   # last 100 records (default 50)
synthadoc audit history --json -w my-wiki   # raw JSON for scripting

synthadoc audit cost -w my-wiki             # total tokens + daily breakdown, last 30 days
synthadoc audit cost --days 7 -w my-wiki    # weekly view
synthadoc audit cost --json -w my-wiki      # {total_tokens, total_cost_usd, daily: [...]}

synthadoc audit events -w my-wiki           # table: timestamp, job_id, event type, metadata
synthadoc audit events --json -w my-wiki    # raw JSON
```

> **Note:** In v0.1, `cost_usd` for ingest was always `$0.0000`. In v0.2, query costs are tracked using an approximate rate. Per-model pricing tables are planned for a future release — token counts are always accurate.

### Cache management

```bash
# Remove all cached LLM responses
# Output: "Cache cleared: N entries removed."
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

Synthadoc writes three log artefacts per wiki: `log.md` (human-readable Markdown, open in Obsidian), `synthadoc.log` (JSON lines, rotate-by-size, grep with `jq`), and `audit.db` (append-only SQLite — source hashes, cost records, job history).

For the full field reference, log levels, rotation config, OTel integration, and audit query examples see [docs/design.md — Logs and Audit Trail](docs/design.md#logs-and-audit-trail).

---

## Customization

### Custom skills (new file formats)

Subclass `BaseSkill` (Apache-2.0 — no AGPL obligation on your skill code), drop the file in `<wiki-root>/skills/` or `~/.synthadoc/skills/`, and Synthadoc hot-loads it on the next ingest. Skills can match by file extension or intent prefix (supports any Unicode text, including Chinese/Japanese/Arabic prefixes).

### Custom LLM providers

Subclass `LLMProvider` from `synthadoc/providers/base.py` (Apache-2.0) and place it in `~/.synthadoc/providers/` or the wiki `providers/` directory.

### Hooks

Shell commands (any language) that fire on `on_ingest_complete` and `on_lint_complete`. Receive a JSON context on stdin. Set `blocking = true` to gate the operation on the hook's exit code.

### Cache

Three cache layers (embedding, LLM response, provider prompt cache). Cache invalidates automatically on source file change (SHA-256). Force a fresh call with `--force` or wipe all responses with `synthadoc cache clear -w my-wiki`.

### Per-wiki AGENTS.md

Edit `<wiki-root>/AGENTS.md` to give the LLM domain-specific instructions — terminology, page naming conventions, what to cross-reference. Highest-priority instruction source for every agent run against this wiki.

For full examples, API signatures, and intent-dispatch config see [docs/design.md — Customization](docs/design.md#customization).

---

## Links

- Design document: [docs/design.md](docs/design.md)
- Quick-Start Guide: [docs/user-quick-start-guide.md](docs/user-quick-start-guide.md)
- Contributing: [CONTRIBUTING.md](CONTRIBUTING.md)
- Issues: [GitHub Issues](../../issues)
