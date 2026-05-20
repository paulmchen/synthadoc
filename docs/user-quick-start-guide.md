# Synthadoc User Quick-Start Guide

**Version: v0.4.0 (Community Edition)**

This guide walks you through the **History of Computing** demo wiki — a fully wired
Synthadoc environment with 13 pre-built pages and six raw source files that cover every
major engine feature. No setup beyond following the steps below is required.

> **Before you start:** complete [README Installation Steps 1–6](../README.md#installation)
> (clone, install, set your API key, install the demo wiki, and start the engine).
> Then come back here.

---

## Table of Contents

1. [Verify the demo server has started](#step-1--verify-the-demo-server-has-started)
2. [Install the Synthadoc plugin](#step-2--install-the-synthadoc-plugin)
3. [Open the vault in Obsidian](#step-3--open-the-vault-in-obsidian)
4. [Review the wiki structure and key files](#step-4--review-the-wiki-structure-and-key-files)
5. [Query the pre-built wiki (CLI + Obsidian)](#step-5--query-the-pre-built-wiki-cli--obsidian)
6. [Batch ingest all demo sources](#step-6--batch-ingest-all-demo-sources)
7. [Resolve a contradiction](#step-7--resolve-a-contradiction)
8. [Fix an orphan page](#step-8--fix-an-orphan-page)
9. [Run the adversarial lint pass](#step-9--run-the-adversarial-lint-pass)
10. [Web search ingestion](#step-10--web-search-ingestion)
11. [Ingest a YouTube video](#step-11--ingest-a-youtube-video)
12. [Enrich the wiki with scaffold](#step-12--enrich-the-wiki-with-scaffold)
13. [Audit features](#step-13--audit-features)
14. [Scheduling recurring operations](#step-14--scheduling-recurring-operations)
15. [Set up ROUTING.md — scoped search](#step-15--set-up-routingmd--scoped-search)
16. [Configure candidates staging](#step-16--configure-candidates-staging)
17. [Build a context pack](#step-17--build-a-context-pack)

**Appendices**

- [Appendix A — Obsidian Plugin Command Reference](#appendix-a--obsidian-plugin-command-reference)
- [Appendix B — Hooks: auto-commit wiki to git](#appendix-b--hooks-auto-commit-wiki-to-git)
- [Appendix C — Switching LLM providers](#appendix-c--switching-llm-providers)
- [Appendix D — Tavily web search key](#appendix-d--tavily-web-search-key)
- [Appendix E — Configuration](#appendix-e--configuration)
- [Appendix G — Using a Coding Tool as Your LLM Provider](#appendix-g--using-a-coding-tool-as-your-llm-provider)
- [Appendix H — BM25 Routing Performance Benchmarks](#appendix-h--bm25-routing-performance-benchmarks)

---

## Step 1 — Verify the demo server has started

If you ran `synthadoc serve -w history-of-computing` or
`synthadoc serve -w history-of-computing --background` in the README, the server
should already be listening on port 7070. Confirm it is up:

```bash
synthadoc status -w history-of-computing
```

Expected output:

```
Wiki:         /home/user/wikis/history-of-computing
Pages:        13
Jobs pending: 0
Jobs total:   0
```

Or probe the health endpoint directly:

```bash
curl http://127.0.0.1:7070/health
# → {"status":"ok"}
```

If neither responds, start the server now:

```bash
# Foreground (terminal stays attached — logs stream to console)
synthadoc serve -w history-of-computing

# Background (terminal is released — logs go to wiki log file)
synthadoc serve -w history-of-computing --background
```

![synthadoc serve startup banner](png/synthadoc-serve.png)

The banner confirms the port, wiki path, active LLM provider/model, and PID. If you see
`Warning: TAVILY_API_KEY is not set`, web search (Step 10) will not work — see
[Appendix D — Tavily web search key](#appendix-d--tavily-web-search-key).

If the server does not start, the most common cause is the port already being in use.
Check `<wiki-root>/.synthadoc/config.toml` for `[server] port` and use `--port N` to
override if needed.

> To use Claude Code or Opencode as your LLM provider instead of a direct API key, see [Appendix G](#appendix-g--using-a-coding-tool-as-your-llm-provider).

### Set your active wiki (do this once)

```bash
synthadoc use history-of-computing
```

From this point on, every command in this guide omits `-w history-of-computing` — the active wiki is resolved automatically.

To see which wiki is active at any time:

```bash
synthadoc use
```

---

## Step 2 — Install the Synthadoc plugin

The plugin ships pre-built — no build step required. Run this command before opening
Obsidian — it copies the plugin files directly into the vault's plugins folder:

```bash
synthadoc plugin install history-of-computing
```

> **Note:** The wiki must be registered first via `synthadoc install` before running
> this command. The installer looks up the wiki's path from the registry.

That's it for the CLI steps. Now open Obsidian.

---

## Step 3 — Open the vault in Obsidian

**Obsidian must already be installed** — download from **[obsidian.md](https://obsidian.md)** if not.

### 1. Open the vault

In Obsidian: **Open folder as vault** → select the installed wiki folder:

- **Windows:** `%USERPROFILE%\wikis\history-of-computing`
- **Linux / macOS:** `~/wikis/history-of-computing`

> **Tip — show all file types:** By default Obsidian hides file types it does not
> natively understand (`.xlsx`, `.pptx`, etc.). To show them: **Settings → Files and
> links → Show all file types → on**.

### 2. Install Dataview

**Dataview** is an Obsidian community plugin that powers the live dashboard in `wiki/dashboard.md`.

1. **Settings** (gear icon, bottom-left) → **Community plugins**
2. Toggle **Turn on community plugins** if it is off
3. Click **Browse** → search `Dataview` → **Install** → **Enable**
4. Close settings

### 3. Enable the Synthadoc plugin

The plugin files are already in place from Step 2. Obsidian just needs to activate them:

1. **Settings → Community plugins** → find **Synthadoc** → toggle **on**
2. Click the gear icon next to the Synthadoc entry
3. Set **Server URL** to `http://127.0.0.1:7070`
4. Close settings

The **Synthadoc ribbon icon** (book icon on the far-left sidebar) confirms the plugin is
active. All Synthadoc commands are reachable via the Command Palette (`Ctrl/Cmd+P` →
type `Synthadoc`).

![Synthadoc ribbon icon](png/synthadoc-ribbon-icon.png)

![Obsidian vault with pre-built wiki](png/synthadoc-vault-demo.png)

> **Dataview cache:** If the dashboard disagrees with `synthadoc lint report`, drop the
> cache: `Ctrl/Cmd+P` → **Dataview: Drop all cached file metadata**, then reopen the
> dashboard. The CLI report is always authoritative.

---

## Step 4 — Review the wiki structure and key files

Open the vault explorer. The key files and folders:

```
history-of-computing/
  wiki/                   ← compiled Markdown pages (open these in Obsidian)
    index.md              ← table of contents with [[wikilinks]] to every page
    dashboard.md          ← live Dataview tables — orphans, contradictions, recent pages
    purpose.md            ← scope definition — what belongs in this wiki and what to skip
    overview.md           ← LLM-generated 2-paragraph summary of the entire wiki
    alan-turing.md        ← example pre-built topic page
    grace-hopper.md       ← ...and so on for each of the 13 pre-built pages
  raw_sources/            ← source documents to ingest (PDF, PPTX, XLSX, PNG, MD)
  AGENTS.md               ← LLM instructions — domain guidelines for ingest and query
  log.md                  ← human-readable activity log of every ingest and lint event
  .synthadoc/
    config.toml           ← per-wiki settings (port, LLM provider, cost limits)
    audit.db              ← immutable audit trail (ingest history, costs, events)
    jobs.db               ← job queue (persistent across server restarts)
    cache.db              ← LLM response cache (reduces repeat spend)
```

**Open these files in Obsidian now:**


| File                  | What to look at                                                   |
| --------------------- | ----------------------------------------------------------------- |
| `wiki/index.md`       | Pre-generated category structure with`[[wikilinks]]` to each page |
| `wiki/dashboard.md`   | Live Dataview tables — will populate after Steps 6–8            |
| `wiki/alan-turing.md` | YAML frontmatter:`status`, `confidence`, `tags`, `sources[]`      |
| `AGENTS.md`           | Domain-specific guidelines the LLM reads on every ingest          |
| `wiki/purpose.md`     | In-scope / out-of-scope definition for History of Computing       |

**Graph view** (`Ctrl/Cmd+G`): the 10 pre-built pages should appear as interconnected
nodes. `index` and `dashboard` connect to everything; topic pages cluster by cross-links.

![Obsidian Graph View — pre-built wiki](png/synthadoc-graph-view.png)

---

## Step 5 — Query the pre-built wiki (CLI + Obsidian)

### CLI queries

The wiki already has 13 pages on computing history — query them before ingesting anything:

```bash
synthadoc query "How did Alan Turing influence modern computers?"
synthadoc query "What is Moore's Law and why does it matter?"
synthadoc query "How did Unix influence the open-source movement?"
```

Each answer cites `[[wikilinks]]` pointing to the source pages.

### Compound and multi-part queries

Synthadoc automatically decomposes complex questions into focused sub-queries, retrieves
pages for each part in parallel, then synthesises a single merged answer:

```bash
# Two-part question — decomposes into two independent BM25 searches
synthadoc query "Compare Alan Turing's theoretical contributions with Von Neumann's architectural contributions."

# Multi-hop causal question — automatically decomposed
synthadoc query "How did Moore's Law shape both hardware design and software expectations over time?"
```

The server log shows the decomposition:

```
query decomposed into 2 sub-question(s):
  "Alan Turing theoretical contributions" | "Von Neumann architectural contributions"
```

Simple single-topic questions decompose to one sub-question and behave identically to
a direct query — no extra LLM cost.

> **Slow provider?** Reasoning models (e.g. MiniMax M2.x) can take longer to respond.
> If you see a timeout error, pass `--timeout 120`:
>
> ```bash
> synthadoc query "How did Moore's Law shape hardware design?" --timeout 120
> ```

### Knowledge gap detection

If the wiki does not cover a topic, Synthadoc detects the gap automatically:

```bash
synthadoc query "What is quantum error correction?"
```

Expected output (example):

```
No relevant pages found on this topic.

[!tip] Knowledge Gap Detected
Your wiki doesn't have enough on this topic yet. Enrich it with a web search:

  synthadoc ingest "search for: quantum error correction methods"
  synthadoc ingest "search for: quantum computing hardware qubits"
```

The suggested search strings are generated automatically. Run one of the suggestions
after Step 10 to fill the gap.

![CLI query result with knowledge gap callout](png/cli-gap-detection.png)

### Query from Obsidian

Open the Command Palette (`Ctrl/Cmd+P`) → `Synthadoc: Query: ask the wiki...` → type a
question → press `Ctrl/Cmd+Enter`. The answer appears in a responsive modal with
clickable `[[wikilinks]]`.

![Obsidian query modal with answer](png/ui-gap-detection.png)

### Aliases — alternative names for a page

Every wiki page (pre-built or ingest-created) has an `aliases` field in its frontmatter.
It starts empty and is visible in Obsidian's **Properties** panel. Add alternative
names or abbreviations so the query engine can match them without knowing the exact page title.

**Try it now with `wiki/alan-turing.md`:**

1. Open `wiki/alan-turing.md` in Obsidian
2. In the **Properties** panel, click the `aliases` field and add one or more names:

```yaml
---
title: Alan Turing
aliases:
  - Turing
  - father of computer science
  - Turing machine inventor
---
```

3. Save the file, then query using an alias instead of the page title:

```bash
synthadoc query "What did Turing contribute to computing?"
# "Turing" expands to the alan-turing slug before BM25 runs
```

Aliases are matched case-insensitively. Longest match wins — so if two pages each define
an alias and one is a longer substring of the query, the longer one takes precedence.

---

## Step 6 — Batch ingest all demo sources

The six source files in `raw_sources/` are designed to demonstrate every ingest scenario:


| File                               | Skill      | Scenario                                                                                                                                                                 |
| ---------------------------------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `turing-enigma-decryption.pdf`     | `pdf`      | **A — Clean merge**: enriches `alan-turing` with Bletchley Park and Bombe detail                                                                                        |
| `computing-pioneers-timeline.xlsx` | `xlsx`     | **A — Clean merge**: structured two-sheet timeline; enriches multiple pages                                                                                             |
| `cs-milestones-overview.pptx`      | `pptx`     | **A — Clean merge + new pages**: 6-slide deck; creates `eniac`, `transistor-and-moores-law`, `internet-history`; enriches `ada-lovelace`, `alan-turing`, `grace-hopper` |
| `first-compiler-controversy.pdf`   | `pdf`      | **B — Conflict**: contradicts `grace-hopper` (A-0 vs FORTRAN dispute)                                                                                                   |
| `quantum-computing-primer.png`     | `image`    | **A — New page**: vision LLM extracts key concepts; creates `quantum-computing`                                                                                         |
| `konrad-zuse-z3-computer.md`       | `markdown` | **C — Orphan**: specific niche topic; creates `konrad-zuse` with no inbound links                                                                                       |

### Run batch ingest

**CLI:**

```bash
synthadoc ingest --batch raw_sources/
```

**Obsidian:** Command Palette → `Synthadoc: Ingest: all sources in folder`

Both enqueue one job per file. Watch them:

```bash
synthadoc jobs list
```

![synthadoc jobs list terminal output](png/job-list-terminal.png)

Wait until all six show `completed`. Filter by status if needed:

```bash
synthadoc jobs list --status pending
synthadoc jobs list --status completed
```

Or from Obsidian: Command Palette → `Synthadoc: Jobs...` → use the status-filter checkboxes. The table defaults to newest jobs first; click **Status**, **Operation**, or **Created** headers to re-sort.

![Obsidian Jobs list modal with status filter dropdown](png/synthadoc-jobs-modal.png)

### Verify the results

Once all jobs complete, open **Graph view** (`Ctrl/Cmd+G`) — new nodes appear for the
ingested topics and link into the existing graph.

![Obsidian Graph View after batch ingest](png/synthadoc-graph-after.png)

Run a few queries that use the new content:

```bash
synthadoc query "What was the Bombe machine and who built it?"
synthadoc query "Who invented FORTRAN and when?"
synthadoc query "What did Konrad Zuse contribute to computing history?"
```

---

## Step 7 — Resolve a contradiction

After `first-compiler-controversy.pdf` is processed, `wiki/grace-hopper.md` will have:

```yaml
status: contradicted
```

The PDF argues that Hopper's A-0 was a loader rather than a compiler, and that FORTRAN
(1957) was the first production compiler — contradicting the existing page.

**Check via CLI:**

```bash
synthadoc lint report
```

```
Contradicted pages (1) - need review:

  grace-hopper
    -> Open wiki/grace-hopper.md, resolve the conflict, then set status: active
    -> Or re-run: synthadoc lint run --auto-resolve
```

**In Obsidian:** open `wiki/dashboard.md` — `grace-hopper` appears in the
**Contradicted pages** Dataview table. The Properties panel shows `status: contradicted`.

![Dashboard showing contradicted page](png/synthadoc-wiki-conflict.png)

### Option 1 — Manual resolution (recommended first time)

1. Open `wiki/grace-hopper.md` in Obsidian
2. Edit the body to reflect a nuanced view — Hopper pioneered automated code generation
   with A-0; Backus and IBM delivered the first production compiler with FORTRAN in 1957
3. Change `status: contradicted` → `status: active` in the Properties panel
4. Save — the Contradicted pages table clears immediately

### Option 2 — LLM auto-resolve

```bash
synthadoc lint run --auto-resolve
synthadoc jobs status <job-id>
```

The LLM proposes a resolution, appends it as a `**Resolution:**` block, and sets
`status: active`. Review the result in Obsidian and edit if needed.

Or from Obsidian: Command Palette → `Synthadoc: Lint: run with auto-resolve`.

> **Dashboard still showing the contradiction?** Dataview may be serving stale metadata.
> Drop the cache: `Ctrl/Cmd+P` → **Dataview: Drop all cached file metadata**, then reopen
> `dashboard.md`. If `synthadoc lint report` shows "all clear", the file is already
> correct — Dataview just has not caught up yet.

---

## Step 8 — Fix an orphan page

The pre-built demo wiki includes `wiki/ada-lovelace.md`, but no other page links to it.
That makes it an **orphan** — a page with no inbound `[[wikilinks]]`.

**Check via CLI:**

```bash
synthadoc lint report
```

```
Orphan pages (2) - no inbound links:

  ada-lovelace
    -> Add [[ada-lovelace]] to a related content page, e.g.:
         - [[ada-lovelace]] — computing history, programming languages, operating systems, hardware innovation
  quantum-computing-primer
    -> Add [[quantum-computing-primer]] to a related content page, e.g.:
         - [[quantum-computing-primer]] — Quantum Computing Primer
```

**In Obsidian:** open `wiki/dashboard.md` — `ada-lovelace` and `quantum-computing-primer` appear in the **Orphan pages**
Dataview table.

> **Note on Graph view:** Obsidian's Graph view draws edges for both inbound and outbound
> links, so an orphan page that contains its own `[[wikilinks]]` to other pages may appear
> connected. Synthadoc defines an orphan as having **no inbound links** — always use
> `synthadoc lint report` as the authoritative check.

### Option 1 — Link it (recommended)

Open `wiki/programming-languages-overview.md` and add a reference:

```
Ada Lovelace is widely credited as [[ada-lovelace|the first programmer]], having written
the first algorithm intended to be executed by Charles Babbage's Analytical Engine in 1843.
```

Save — the orphan disappears from the dashboard immediately.

### Option 2 — Delete and re-ingest later

If the page content quality is poor, delete `wiki/ada-lovelace.md` from Obsidian and
pull in a fresh source via web search:

```bash
synthadoc ingest "search for: Ada Lovelace contributions to computing history"
```

### Deleting a page and cleaning up its references

When you delete a wiki page from Obsidian, any `[[wikilinks]]` pointing to it in other
pages become dangling references. Run lint to remove them automatically:

```bash
synthadoc lint run
```

Lint scans every page for links whose target no longer exists:

- **List items** whose only content is the dangling link are removed entirely, e.g.
  `- [[deleted-page]] — some description` disappears from the page.
- **Inline references** such as `as described in [[deleted-page]]` are unlinked — the
  brackets are stripped and the display text is kept.

The number of pages cleaned up is shown in the lint output and recorded in `log.md`.

---

## Step 9 — Run the adversarial lint pass

The standard lint checks (contradictions, orphans, dangling links) catch structural problems.
The **adversarial lint pass** adds a second LLM pass that plays devil's advocate against every
page — flagging overstated claims, unsupported assertions, and statements that are plausible
but hard to verify.

The adversarial pass runs automatically as part of every `synthadoc lint run`. No extra flag is
needed.

### Run lint (with adversarial pass)

```bash
synthadoc lint run
synthadoc jobs list           # watch progress
synthadoc lint report         # view results when complete
```

The pre-built pages already contain the kinds of sweeping historical claims an adversarial
reviewer will flag — no additional ingest is needed before this step, though running Step 6
first gives the adversarial pass more content to work with.

Sample output for the history-of-computing demo wiki:

```
Contradicted pages (0)
Orphan pages (0)

Adversarial warnings (3):

  alan-turing
    Claim:   "Turing's work at Bletchley Park shortened the war by two to four years."
    Concern: This figure is widely cited but historically contested — it is a counterfactual
             estimate; different historians give figures ranging from one year to "possibly
             none" depending on model assumptions.
    Sources: raw_sources/turing-enigma-decryption.pdf
    Re-ingest: synthadoc ingest raw_sources/turing-enigma-decryption.pdf

  artificial-intelligence-history
    Claim:   "These systems exhibit emergent capabilities that were not explicitly programmed."
    Concern: "Emergence" in large language models is disputed — several researchers argue
             that capability gains are smooth and predictable at scale, and that the label
             "emergent" reflects measurement choices rather than a genuine phase transition.
    Sources: public-domain/mccorduck-machines-who-think.txt
    Re-ingest: synthadoc ingest "search for: emergent capabilities LLMs debate Schaeffer 2023"

  personal-computer-revolution
    Claim:   "IBM's decision to build the PC from off-the-shelf parts ... was the most
             consequential business decision of the era."
    Concern: An unsupported superlative — Microsoft's retention of the MS-DOS licence and
             Intel's exclusive CPU supply deal were equally pivotal; "most consequential"
             requires a comparison the text does not make.
    Sources: public-domain/ceruzzi-history-modern-computing.txt
    Re-ingest: synthadoc ingest "search for: IBM PC open architecture business impact history"
```

### What each warning means

Each adversarial warning has two parts:

| Field | Meaning |
|---|---|
| **Claim** | The exact sentence or phrase flagged as potentially problematic |
| **Concern** | Why the adversarial reviewer flagged it — the specific doubt |

The adversarial LLM is deliberately skeptical. Not every warning requires action — some claims
are defensible with context the LLM does not have. Read each concern before deciding what to do.

### What to do with a warning

| Situation | Action |
|---|---|
| Claim is accurate, concern is addressed by other pages | Do nothing — the wiki is fine |
| Claim is a genuine overstatement | Edit the page in Obsidian and soften the language |
| Claim needs better sourcing | Re-ingest the original source: `synthadoc ingest <file>` |
| Page quality is poor overall | Delete the page and re-ingest: `synthadoc ingest <new-source>` |

### Hands-on exercise

The `alan-turing` warning flags a contested counterfactual. Fix it:

1. Open `wiki/alan-turing.md` in Obsidian
2. Find the sentence about shortening the war (in the **Wartime Contributions** section)
3. Replace the specific estimate with qualified language:
   ```
   Historians credit Turing's Bombe with dramatically accelerating Allied codebreaking,
   though estimates of its effect on the war's duration vary widely.
   ```
4. Save — the next lint run will re-evaluate the page and the warning will clear

### Verify the warning cleared

```bash
synthadoc lint run
synthadoc lint report
```

The `alan-turing` adversarial warning should no longer appear.

### View warnings in Obsidian

Open the Command Palette (`Ctrl/Cmd+P`) → `Synthadoc: Lint: report` → click the
**Adversarial** tab. Each warning shows the flagged claim, the concern, and a suggested
re-ingest command derived from the page's source files.

> **Skip the adversarial pass:** If you want a fast structural-only lint, open
> `Synthadoc: Lint: run...` and tick **Skip adversarial review**. This also clears any
> existing `lint_warnings` from frontmatter so stale warnings do not linger.

### Optional — configure a dedicated adversarial model

By default the adversarial pass uses the same model as the rest of lint. For large wikis,
point it at a faster or cheaper model to keep costs down:

```toml
# config.toml
[agents]
lint        = { provider = "groq",   model = "llama-3.3-70b-versatile" }
adversarial = { provider = "groq",   model = "gemma2-9b-it" }   # faster, cheaper judge
```

The two models are intentionally different — a separate model acting as judge reduces the
self-serving bias that occurs when a model reviews its own output.

---

## Step 10 — Web search ingestion

> **Requires `TAVILY_API_KEY`** — see [Appendix D](#appendix-d--tavily-web-search-key).
> Without it, web search jobs fail with `[ERR-SKILL-004]`. All other features work normally.

### How web search decomposition works

Synthadoc **decomposes web search topics** into multiple focused keyword sub-queries
before hitting Tavily. Each sub-query fires a separate parallel search, URLs are
deduplicated across all results, and each is enqueued as an individual ingest job.
This produces richer, more targeted pages than a single broad search.

```
Input: "search for: history of ARPANET and internet origins"

Server log:
  web search decomposed into 3 queries:
    "ARPANET creation 1969 DARPA" | "TCP/IP protocol development history" | "internet origins packet switching"

Result: 3 parallel Tavily searches → ~60 URLs ingested vs ~20 from a single search
```

Decomposition falls back gracefully — if the LLM call fails, the original phrase is used as
a single query and the ingest always completes.

### Run a web search ingest

```bash
synthadoc ingest "search for: Dennis Ritchie C programming language Bell Labs history"
synthadoc ingest "search for: ENIAC first general purpose electronic computer history"
```

Each command fans out to up to 20 URL ingest jobs. The commands return immediately —
all processing happens in the background. Watch progress with:

```bash
synthadoc jobs list
```

> **How long does it take?**
>
> - **Free-tier Gemini (15 RPM) or Groq:** Two searches produce ~20–40 LLM calls. The
>   server retries automatically when the rate limit is hit (you will see
>   `Rate limit (429) — waiting 60 s` in the server log — this is normal). Expect
>   **3–8 minutes** for both searches to fully complete.
> - **Paid tier (Gemini paid, MiniMax, Anthropic, OpenAI):** No rate-limit retries.
>   Both searches typically finish in **under 2 minutes**.

Pages such as `dennis-ritchie`, `eniac-history`, and related topics will be created or
enriched. The `wiki/overview.md` page is regenerated automatically after each batch
completes.

### Control the scope

Limit how many URLs are enqueued (default: 20):

```bash
synthadoc ingest "search for: quantum computing IBM Google" --max-results 5
```

**Batch via manifest file:** the demo wiki ships a `sources.txt` at the wiki root (outside `raw_sources/` — a `.txt` inside that folder would be treated as a text document rather than a manifest). It already contains these web search entries alongside YouTube and PDF sources:

```
search for: Dennis Ritchie C programming language Bell Labs history
find on the web: Linus Torvalds Linux kernel creation 1991
search for: Ada Lovelace first programmer Analytical Engine Babbage
look up: history of ARPANET and internet origins
```

Ingest all sources at once:

```bash
synthadoc ingest --file sources.txt
```

### Web search from Obsidian — live view

Open the Command Palette → `Synthadoc: Ingest: web search...`:

1. Type a topic — e.g. `Linus Torvalds Linux kernel creation 1991`
2. Set **Max results** (1–50, default 20) to control scope
3. Adjust **Poll interval** if desired (default: 2000 ms)
4. Press `Ctrl/Cmd+Enter` or click **Search**

The modal transitions to a live view:

- **Searching the web…** — while Tavily fetches
- **Found N URLs — ingesting…** — as fan-out jobs are created
- **Ingesting N URLs… (M done)** — counting completed child jobs
- A **Pages** list grows in real time as each URL ingest completes
- **Errors** (blocked domains, 404s) appear in red
- **Done — N page(s) written.** when all jobs settle

![Obsidian web search live view](png/synthadoc-search-live-view.png)

The modal prepends `search for:` automatically — just type the topic, no prefix needed.

---

## Step 11 — Ingest a YouTube video

Pass any YouTube URL directly — the transcript is extracted automatically from the
YouTube caption system (no API key, no audio download). Both the full URL and the
short-link form (`https://youtu.be/...`) are accepted:

```bash
synthadoc ingest "https://www.youtube.com/watch?v=O5nskjZ_GoI"
```

This ingests *Early Computing: Crash Course Computer Science #1*, which covers Hollerith,
Babbage, Lovelace, and the first programmable machines — a natural fit for the demo wiki.
The YouTube entries in `sources.txt` (see Step 10) include this video, so running
`synthadoc ingest --file sources.txt` handles it alongside the web searches.

The wiki page opens with an **executive summary** — a brief description of what the video
covers, the main topics as bullet points, and the key takeaway — so you can assess
relevance at a glance. The full timestamped transcript follows for precise cross-referencing.

> **Captions required** — the video must have captions (auto-generated or manually added).
> Check by opening the video on YouTube → `...` → **Show transcript**. If no transcript
> panel appears, the source is skipped with a warning and ingestion continues.

> **Short vs. long videos** — short videos produce a single wiki page. Long videos are
> chunked automatically by the existing `max_pages_per_ingest` limit.

Watch progress:

```bash
synthadoc jobs list
```

> **Tavily search + YouTube** — if Tavily returns YouTube URLs as web search results, they
> are automatically routed to the YouTube transcript skill. No extra steps needed.

---

## Step 12 — Enrich the wiki with scaffold

After batch ingest, the wiki has grown from 10 pre-built pages to 12 or more. **Scaffold**
reads the current wiki state and uses the LLM to regenerate the structure files —
`wiki/index.md`, `AGENTS.md`, and `wiki/purpose.md` — so they reflect what the wiki has
actually become. Existing pages that are already linked in `index.md` are detected as
**protected slugs** and preserved; only unlinked and new categories are refreshed.

### Run scaffold

```bash
synthadoc scaffold
```

Expected output:

```
Reading current wiki content…
Generating domain-specific scaffold (History of Computing)…
  Protected slugs: alan-turing, grace-hopper, von-neumann-architecture, unix-history, … (10 pages)
  Scaffold complete — domain-specific content generated.
wiki/index.md updated
AGENTS.md updated
wiki/purpose.md updated
```

Open `wiki/index.md` in Obsidian — it now has richer category headings that reflect the
full post-ingest wiki (e.g. **Pioneers and Visionaries**, **Hardware Milestones**,
**Software and Languages**, **European Computing**, **Emerging Technology**).

### Re-run scaffold at any time

As the wiki grows, re-running scaffold keeps the index structure current:

```bash
synthadoc scaffold
```

`config.toml` and `dashboard.md` are **never touched** by scaffold.

### Schedule scaffold automatically

To keep the index fresh without manual intervention:

```bash
# Weekly scaffold refresh — every Sunday at 4 AM
synthadoc schedule add --op "scaffold" --cron "0 4 * * 0"
```

### Protect custom content with the scaffold marker

By default, re-running scaffold rewrites the entire `index.md`. If you want to add your own
intro text, notes, or links that survive future scaffold runs, add the marker on its own line:

```markdown
My custom wiki intro — maintained by hand.

<!-- synthadoc:scaffold -->

## Pioneers and Visionaries
- [[alan-turing]]
...
```

Everything **above** the marker is your protected zone — scaffold never touches it.
Everything **below** is rewritten each time. If the marker is absent, scaffold rewrites
the whole file as before.

---

## Step 13 — Audit features

The `synthadoc audit` commands query the append-only `audit.db` — no `sqlite3` required.

### Ingest history

```bash
synthadoc audit history
```

Shows the last 50 ingest records: timestamp, source file, wiki pages created/updated,
token count, and cost. Use `--limit N` (or `-n N`) for more records and `--json` for machine-readable output.

![synthadoc audit history output](png/synthadoc-audit-history.png)

### Cost summary

```bash
synthadoc audit cost
```

Expected output:

```
Period: last 30 days
Total tokens : 22,400
Total cost   : $0.143
Sources processed: 6
Avg cost/source  : $0.024
```

Pass `--days 7` for a weekly view. Per-model cost tracking is fully live in v0.2.0.

![synthadoc audit cost output](png/synthadoc-audit-cost.png)

### Query history

```bash
synthadoc audit queries
```

Shows recent questions asked, how many sub-questions each was decomposed into, token
usage, and per-query cost. Especially useful after running the compound queries in Step 5.

### Audit events

```bash
synthadoc audit events
```

Expected after Steps 6–8:

```
2026-04-21 10:12  contradiction_found   grace-hopper ← first-compiler-controversy.pdf
2026-04-21 10:14  auto_resolved         grace-hopper (confidence: 0.91)
```

Records every contradiction detection, auto-resolution, and cost gate trigger.

![synthadoc audit events output](png/synthadoc-audit-events.png)

---

## Step 14 — Scheduling recurring operations

Hooks react to events that already happened. The scheduler goes the other direction —
it proactively triggers operations on a timer, keeping the wiki fresh automatically.

### Register a nightly batch ingest

```bash
synthadoc schedule add \
  --op "ingest --batch raw_sources/" \
  --cron "0 2 * * *" \
 
```

This registers a 2 AM daily ingest directly with the OS scheduler (`crontab` on
macOS/Linux, Task Scheduler on Windows). No background daemon required.

### Register a weekly lint pass + weekly scaffold refresh

```bash
synthadoc schedule add --op "lint run" --cron "0 3 * * 0"
synthadoc schedule add --op "scaffold" --cron "0 4 * * 0"
```

### Verify

```bash
synthadoc schedule list
```

Expected:

```
sched-a3f1b2c4  0 2 * * *  ingest --batch raw_sources/
sched-b7e9d012  0 3 * * 0  lint run
sched-c9f3e201  0 4 * * 0  scaffold
```

### Clean up (demo only)

Remove the scheduled jobs so they do not run after the demo:

```bash
synthadoc schedule remove sched-a3f1b2c4
synthadoc schedule remove sched-b7e9d012
synthadoc schedule remove sched-c9f3e201
```

> **Production use:** for always-on scheduling, run `synthadoc serve` as a background
> service (systemd, launchd, or Windows Service) so the server is available when the OS
> fires the scheduled task.

---

## Step 15 — Set up ROUTING.md — scoped search

As your wiki grows, BM25 searches the full corpus for every query. **ROUTING.md** groups pages
into named topic branches so queries only search the most relevant slice — reducing noise,
improving retrieval precision, and significantly cutting search latency on large wikis (see
[Appendix H](#appendix-h--bm25-routing-performance-benchmarks) for measured results).

![ROUTING.md scoped query flow](png/synthadoc-routing.png)

### Generate ROUTING.md from your current index

```bash
synthadoc routing init
```

This reads the `## Section` headings in `wiki/index.md` and writes `ROUTING.md` at the wiki
root. Example output:

```
ROUTING.md created — 5 branches, 12 slugs.
```

Open `ROUTING.md` — it looks like this:

```markdown
## Pioneers and Visionaries
- [[alan-turing]]
- [[grace-hopper]]
- [[ada-lovelace]]

## Hardware Milestones
- [[eniac]]
- [[von-neumann-architecture]]
```

### Edit and extend

Add new branches or move slugs by hand. ROUTING.md is just a Markdown file — the format is
`## BranchName` headings with `- [[slug]]` entries. Each slug should appear in exactly one branch.

If you accidentally list the same slug under two branches, the search result is still correct — `bm25_search` converts the scoped slug list to a set before scoring, so the page is never double-counted. However, the branch assignment becomes ambiguous: a query that picks either branch will find the page regardless of which one was intended. Use `routing validate` to catch these duplicates before they cause confusion.

### Validate and clean

After deleting wiki pages, some slugs in ROUTING.md may dangle. `routing validate` also reports slugs that appear in more than one branch:

```bash
synthadoc routing validate   # report dangling slugs and cross-branch duplicates (dry run)
synthadoc routing clean      # remove dangling slugs
```

Example output when a duplicate is found:

```
Issues in ROUTING.md (1):
  [Hardware]  [[alan-turing]] (duplicate — also in 'People')
```

Fix by removing the entry from the branch where it does not belong, then re-run `validate` to confirm.

### How it works at query time

When the server receives a query it asks the LLM to pick the 1-2 most relevant branches,
then restricts BM25 to only those slugs. If no branch is clearly relevant it falls back to
full-corpus search automatically.

New pages created by ingest are auto-placed into the most appropriate branch.

---

## Step 16 — Configure candidates staging

By default, every ingested source that produces a new page writes it directly to `wiki/`.
**Candidates staging** lets you review new pages before they influence queries and lint.

### Enable staging

```bash
synthadoc staging policy threshold
```

With `threshold` policy, pages whose confidence is below the minimum go to
`wiki/candidates/` instead of `wiki/`. The default minimum is `high`:

```bash
# Lower the bar — medium-confidence pages also go to candidates/
synthadoc staging policy threshold --min-confidence medium
```

Or stage everything for full manual review:

```bash
synthadoc staging policy all
```

Changes take effect on the next ingest job — no server restart needed.

### Review candidates after an ingest run

```bash
synthadoc candidates list
```

Example output:

```
Candidates (3):
  early-internet-history           confidence: medium   ingested: 2026-05-06T14:22:11
  punch-card-era                   confidence: low      ingested: 2026-05-06T14:22:45
  vacuum-tube-computers            confidence: medium   ingested: 2026-05-06T14:23:01
```

![Candidates list in Obsidian](png/synthadoc-candidates.png)

### Promote or discard

```bash
synthadoc candidates promote early-internet-history   # move to wiki/
synthadoc candidates discard punch-card-era           # delete
synthadoc candidates promote --all                    # promote everything
```

### Manage staging from Obsidian

**Set the policy** — Command Palette → `Synthadoc: Staging: manage staging policy...`:

- The modal shows the current policy in plain language at the top.
- Click **Off**, **All**, or **Threshold** in the segmented control.
- When **Threshold** is selected, a second control appears — pick **High**, **Medium**, or **Low** as the minimum confidence.
- Click **Save**. The status block updates immediately to confirm the change.
- Click **Candidate pages →** at the bottom of the modal to jump straight to the Candidates panel.

**Review and promote candidates** — Command Palette → `Synthadoc: Candidates: review candidate pages...`:

- The modal lists every staged page with its slug, colour-coded confidence badge, and ingest timestamp.
- Check individual rows and click **Promote Selected** or **Discard Selected**.
- Use **Promote All** or **Discard All** to act on every candidate at once.
- The table reloads after each action, so the count stays current.
- Click **← Staging policy** at the bottom to jump back to the Staging modal.

### Turn staging off

```bash
synthadoc staging policy off
```

Or from Obsidian: `Synthadoc: Staging: manage staging policy...` → select **Off** → **Save**.

---

## Step 17 — Build a context pack

A **context pack** is a token-bounded evidence bundle assembled from the wiki. It decomposes your goal into sub-questions, runs parallel BM25 searches across the wiki, and packs the highest-scoring excerpts into a single cited Markdown document within a token budget.

### Build a pack from the CLI

```bash
synthadoc context build "early computing pioneers"
```

Output is Markdown printed to the terminal:

```markdown
# Context Pack: early computing pioneers
Generated: 2026-05-07T09:14:22
Token budget: 4000 | Used: 1823

---

## [[alan-turing]] — relevance: 3.42
> Alan Turing developed the theoretical basis of modern computation through his 1936 paper
> on computable numbers. He proposed the concept of a universal machine capable of simulating
> any algorithm...
Source: `wiki/alan-turing.md` | Confidence: high | Tags: mathematics, computation

## [[grace-hopper]] — relevance: 2.91
> Grace Hopper pioneered compiler development and coined the term debugging after finding
> a moth in a relay. Her work on COBOL brought programming to business users...
Source: `wiki/grace-hopper.md` | Confidence: high | Tags: programming, navy

## [[ada-lovelace]] — relevance: 2.44
> Ada Lovelace wrote what is considered the first algorithm intended for a mechanical
> computer, the Analytical Engine designed by Charles Babbage...
Source: `wiki/ada-lovelace.md` | Confidence: high | Tags: mathematics, history

---

## Omitted — token budget exceeded
- [[charles-babbage]] — ~420 tokens
- [[john-von-neumann]] — ~390 tokens
```

Each entry is cited with its source page, confidence, and tags. Pages that did not fit within the budget are listed in the omitted section.

### Use cases

**Feed into an external LLM prompt** — paste the terminal output directly into Claude.ai, ChatGPT, or any other chat interface as grounded context before asking a question:

```bash
synthadoc context build "transistor history and Moore's Law" | pbcopy   # macOS — copies to clipboard
```

**Save next to a document you are writing** — keep the evidence bundle alongside your draft:

```bash
synthadoc context build "early computing pioneers" --output ~/drafts/computing-brief.md
```

**Pipe into another CLI tool** — chain with any tool that reads from stdin:

```bash
synthadoc context build "Von Neumann architecture" --output /tmp/ctx.md
llm -f /tmp/ctx.md "write a 500-word article based on this"
```

### Adjust the token budget

```bash
synthadoc context build "early computing pioneers" --tokens 2000
```

Set a permanent default in `config.toml`:

```toml
[query]
context_token_budget = 6000
```

---

## What's next?

You have now walked through every major Synthadoc feature on the demo wiki. When you're
ready to build a wiki for your own domain:

- **[README — Creating Your Own Wiki](../README.md#creating-your-own-wiki)** — two commands and you're running

Key differences from the demo:

- `synthadoc install <name> --target <dir> --domain "<your domain>"` generates LLM
  scaffold for your domain at install time (index categories, AGENTS.md, purpose.md)
- Drop your own source files into `raw_sources/` and run batch ingest
- Use web search to fill knowledge gaps as your wiki grows
- Schedule nightly ingests and weekly scaffold refresh to keep it current automatically

---

## Appendix A — Obsidian Plugin Command Reference

All commands are accessible via the Command Palette (`Ctrl/Cmd+P` → type `Synthadoc`).

### Ingest


| Command                            | What it does                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Synthadoc: Ingest...`             | Tabbed modal with four ingest modes: **From URL** (paste a URL, polls live until complete), **All sources in folder** (queues every supported file in `raw_sources/`), **Pick files** (click **Browse…** to choose a folder, click **Scan** to list supported files — `wiki/` sub-folder contents and system files such as `log.md`, `routing.md`, `agents.md`, `readme.md`, `dashboard.md`, `index.md`, `overview.md`, and `claude.md` are excluded automatically with a count shown — then select files and click **Ingest selected**), and **Web search** (type a topic, set max results and poll interval, polls live). |
| `Synthadoc: Ingest: web search...` | Standalone live-polling modal — type a topic, set max results (1–50, default 20) and poll interval (500–10000 ms, default 2000 ms). Shows phase text, live pages list, and URL errors as fan-out jobs complete. `Ctrl/Cmd+Enter` to submit.                                                                                                                                                                                                                |

### Query


| Command                             | What it does                                                                                                                                                                                                                                 |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Synthadoc: Query: ask the wiki...` | Responsive modal — ask a natural-language question, get a markdown answer with clickable`[[wikilinks]]` to source pages. `Ctrl/Cmd+Enter` to submit. If a knowledge gap is detected, shows a callout with suggested `search for:` commands. |

### Lint


| Command                   | What it does                                                                                                                                                                                                             |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `Synthadoc: Lint: run...` | Modal with **Auto-resolve** and **Skip adversarial review** checkboxes. Runs a full lint pass with concurrent adversarial review of every page; polls progress live and reports contradiction, orphan, and adversarial warning counts when complete. Tick **Skip adversarial review** to run lint without the adversarial pass (also clears existing `lint_warnings`). |
| `Synthadoc: Lint: report` | Full lint report in a 3-tab modal — **Contradictions**, **Orphans**, and **Adversarial**. The Adversarial tab shows each flagged claim with its concern and suggested re-ingest commands derived from the page's source files. |

### Jobs


| Command                | What it does                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Synthadoc: Jobs...`   | Job table with status-filter checkboxes (pending, in_progress, completed, failed, skipped, dead, cancelled). Defaults to newest jobs first. Click **Status**, **Operation**, or **Created** column headers to sort — ▲ ascending, ▼ descending, ⇅ unsorted; click again to toggle direction. Auto-refreshes every 10 s (configurable). Paginated at 25 per page. Error details shown inline for failed/dead/cancelled jobs. **Retry selected** button is enabled when one or more checked jobs are failed, dead, or cancelled — click to re-queue them. **Delete selected** removes checked terminal jobs. A **Purge old jobs** footer row lets you enter a day threshold and remove old completed/dead records in one click. |

> **Tip — cancelling a bad batch:** `synthadoc jobs cancel -w <wiki> --yes` marks every
> pending job as `skipped` immediately. Follow up with `synthadoc jobs purge` to remove
> the skipped records.

### Wiki


| Command                                   | What it does                                                                                                                   |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `Synthadoc: Wiki: regenerate scaffold...` | Rewrites`index.md`, `AGENTS.md`, and `purpose.md` using the LLM. Polls job status live. All existing wiki pages are preserved. |

### Audit

| Command               | What it does                                                                                                                                                                                                                                                                                          |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Synthadoc: Audit...` | Tabbed modal with four views: **Query history** — recent questions, sub-question counts, tokens, cost per query. **Ingest history** — source file, wiki page slug, tokens, cost, timestamp. **Events** — contradictions found, auto-resolutions, cost gate triggers (max 1000). **Cost summary** — total tokens + USD with daily breakdown. |

### Routing


| Command                                    | What it does                                                                                                                                                                                                                                                                                                                                              |
| ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Synthadoc: Routing: manage ROUTING.md...` | Modal panel with three buttons. **Init** creates `ROUTING.md` from your current `index.md` branch structure (enabled only when `ROUTING.md` does not exist). **Validate** reports dangling slugs — pages listed in `ROUTING.md` that no longer exist — as a dry-run with no changes made (enabled only when `ROUTING.md` exists). **Clean** removes dangling slugs from `ROUTING.md` and refreshes the preview (enabled only when `ROUTING.md` exists). Results show per-entry `[Branch] [[slug]]` detail rows inline. |

### Staging & Candidates


| Command                                          | What it does                                                                                                                                                                                                                                                                                                  |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Synthadoc: Staging: manage staging policy...`   | Shows the current policy in plain language. A segmented control switches between **Off**, **All**, and **Threshold**. When **Threshold** is selected, a second control sets the minimum confidence (**High** / **Medium** / **Low**). **Save** applies the change immediately. A footer link opens the Candidates panel. |
| `Synthadoc: Candidates: review candidate pages...` | Paginated table (50 per page) of all staged candidate pages. Each row shows the slug, colour-coded confidence badge, and ingest timestamp. Check rows and click **Promote Selected** or **Discard Selected**, or use **Promote All** / **Discard All** to act on every candidate at once. Table reloads after each action. A footer link opens the Staging policy panel. |

### Context packs


| Command                                    | What it does                                                                                                                                                                                                                                                                                                                                              |
| ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Synthadoc: Context: build context pack...` | Enter a goal or question and a token budget (default 4000). Press **Build Context Pack** or `Ctrl/Cmd+Enter`. The server decomposes the goal, retrieves the most relevant wiki pages via BM25, and packs them into a single cited Markdown document within the budget. The result appears in a read-only text area. **Copy to Clipboard** copies it to the OS clipboard; **Save as .md** downloads it as a Markdown file. |

> **UX note:** All modals are draggable and support full text selection and copy-paste.

### Ribbon icon

The Synthadoc ribbon icon (left sidebar) shows live engine status: `✅ online · 12 pages`
or `❌ offline — run 'synthadoc serve'`. Right-click the ribbon to pin it if it is hidden
below other plugin icons.

---

## Appendix B — Hooks: auto-commit wiki to git

Hooks are shell commands triggered on lifecycle events. Wire `git-auto-commit.py` so
every successful ingest produces a git commit.

### One-time setup

**1. Initialise git in the wiki root:**

```bash
cd ~/wikis/history-of-computing
git init
git add .
git commit -m "init: initial wiki snapshot"
```

**2. Copy the hook script:**

```bash
cp /path/to/synthadoc-repo/hooks/git-auto-commit.py .
```

**3. Add to `.synthadoc/config.toml`:**

```toml
[hooks]
on_ingest_complete = "python git-auto-commit.py"
```

**4. Restart the server** to pick up the config change.

### Verify

After the next ingest:

```bash
git log --oneline -3
```

```
a3f1b2c wiki: ingest konrad-zuse-z3-computer.md → created konrad-zuse
d9e4c81 wiki: ingest turing-enigma-decryption.pdf → updated alan-turing
```

> **More hooks:** see [`hooks/README.md`](../hooks/README.md) for the full library and
> contribution guidelines. Available events: `on_ingest_complete`, `on_lint_complete`.

---

## Appendix C — Switching LLM providers

Synthadoc defaults to **Gemini Flash** — free, no credit card, 1 million tokens per day.
Switch by editing `<wiki-root>/.synthadoc/config.toml` and restarting the server.


| Provider    | Env var             | Free tier                                    | Vision          |
| ----------- | ------------------- | -------------------------------------------- | --------------- |
| `gemini`    | `GEMINI_API_KEY`    | **Yes — default** · 15 RPM / 1M tokens/day | Yes             |
| `groq`      | `GROQ_API_KEY`      | Yes — fast Llama, 100K tokens/day           | No              |
| `ollama`    | _(none)_            | Yes — fully local, no rate limits           | Model-dependent |
| `minimax`   | `MINIMAX_API_KEY`   | No — cheapest paid text rates               | No              |
| `anthropic`   | `ANTHROPIC_API_KEY` | No — highest quality, pay-per-token                   | Yes             |
| `openai`      | `OPENAI_API_KEY`    | No — pay-per-token                                    | Yes             |
| `claude-code` | _(none)_            | Yes — uses your Claude Code subscription, no key      | Yes             |
| `opencode`    | _(none)_            | Yes — uses your Opencode subscription, no key         | No              |

> CLI providers (`claude-code`, `opencode`) require no API key but need the tool installed and authenticated in your terminal. Web search still requires `TAVILY_API_KEY`. See [Appendix G](#appendix-g--using-a-coding-tool-as-your-llm-provider) for setup details.

**Change the provider** — edit `.synthadoc/config.toml`:

```toml
# Anthropic
[agents]
default = { provider = "anthropic", model = "claude-sonnet-4-6" }

# Gemini Flash (default)
[agents]
default = { provider = "gemini", model = "gemini-2.5-flash" }

# Groq (fast free tier)
[agents]
default = { provider = "groq", model = "llama-3.3-70b-versatile" }

# MiniMax (cheapest paid, natively multimodal)
[agents]
default = { provider = "minimax", model = "MiniMax-M2.5" }
```

Restart `synthadoc serve`. The startup banner confirms `LLM: <provider>/<model>`.

> **Rate limit tips:**
>
> - **Gemini** free tier: 15 RPM. If you see `429 RateLimitError` during a long ingest, wait 60 s and retry, or switch to Groq or MiniMax.
> - **Groq** free tier: 100K tokens/day — adequate for short demo sessions; heavy web search ingest can exhaust it.
> - **MiniMax:** no free tier, but M2.5 input is ~$0.15/M tokens — roughly half the cost of Gemini 2.5 Flash. M2.5 and M2.7 are natively multimodal (text + image).
> - **Ollama:** fully local, no rate limits. Install from [ollama.com](https://ollama.com); no API key needed.

---

## Appendix D — Tavily web search key

Web search ingestion (Step 10) requires a Tavily API key. Get a free key at
**[tavily.com](https://tavily.com)** (1,000 searches/month, no credit card required).

**Set the key:**

```bash
# Linux / macOS
export TAVILY_API_KEY="tvly-your-key-here"

# Windows (cmd.exe — current session)
set TAVILY_API_KEY=tvly-your-key-here

# Windows (cmd.exe — permanent)
setx TAVILY_API_KEY tvly-your-key-here
```

If this key is absent, the server starts normally but web search jobs fail with
`[ERR-SKILL-004]`. All other features work without it.

---

## Appendix E — Configuration

You do not need to configure anything to run the demo. The demo wiki ships with its own settings and sensible built-in defaults cover everything else. Set your API key env var, run `synthadoc serve`, and go.

Read this appendix when you are ready to run a real wiki or change a default.

### How configuration works

Settings are resolved in three layers — later layers win:

```
1. Built-in defaults          (always applied)
2. ~/.synthadoc/config.toml   (global — your preferences across all wikis)
3. <wiki-root>/.synthadoc/config.toml   (per-project — overrides for one wiki)
```

Neither file is required. If both are absent, the built-in defaults take effect.

### Global config — `~/.synthadoc/config.toml`

**Use this to set preferences that apply to every wiki on your machine** — primarily your default LLM provider and the wiki registry.

```toml
[agents]
default = { provider = "gemini", model = "gemini-2.5-flash" }  # free tier
lint    = { provider = "groq",   model = "llama-3.3-70b-versatile" }  # cheaper for lint

[wikis]
research = "~/wikis/research"
work     = "~/wikis/work"
```

Common reason to edit: switching from the Anthropic default to Gemini Flash (free tier) so all wikis use it without touching each project config.

### Per-project config — `<wiki-root>/.synthadoc/config.toml`

**Use this when one wiki needs different settings from the global default** — a different port, tighter cost limits, wiki-specific hooks, or web search.

```toml
[server]
port = 7071          # required if running more than one wiki simultaneously

[cost]
soft_warn_usd = 0.50
hard_gate_usd = 2.00

[ingest]
fetch_timeout_seconds = 60   # increase if slow sites time out during web search

[web_search]
provider    = "tavily"
max_results = 20

# Optional: enable semantic re-ranking (downloads ~130 MB model once)
# [search]
# vector = true
# vector_top_candidates = 20   # BM25 candidate pool before cosine re-rank

[hooks]
on_ingest_complete = "python git-auto-commit.py"
```

Common reason to edit: each wiki needs its own port when running multiple wikis at the same time.

Full config reference including all keys, defaults, and multi-wiki setup: [docs/design.md — Configuration](design.md#configuration).

---

## Appendix F — Build Your Own Wiki from scratch

This appendix walks through creating a wiki for your own domain — no demo template.

### 1. Install and scaffold

```bash
synthadoc install my-research --target ~/wikis
synthadoc scaffold -w my-research
synthadoc use my-research
```

`scaffold` prompts for a domain description and generates `wiki/index.md`,
`wiki/purpose.md`, and `AGENTS.md` (the LLM's per-ingest context document).

### 2. Start the server

```bash
synthadoc serve -w my-research
```

### 3. Ingest sources

```bash
synthadoc ingest path/to/document.pdf
synthadoc ingest "https://example.com/article"
synthadoc ingest "search for: <your domain topic>"
synthadoc jobs list
```

### 4. Query

```bash
synthadoc query "What are the key themes?"
```

### 5. Lint

```bash
synthadoc lint report
synthadoc lint run --auto-resolve
```

### 6. Open in Obsidian

Open `~/wikis/my-research` as an Obsidian vault.

### Working with multiple wikis

```bash
synthadoc use finance-wiki     # switch active wiki
synthadoc status               # checks finance-wiki
synthadoc status -w legal-wiki # one-off check without switching
synthadoc use                  # confirm which wiki is active
```


| Method                         | Scope                               |
| ------------------------------ | ----------------------------------- |
| `synthadoc use <name>`         | Persistent across terminal sessions |
| `export SYNTHADOC_WIKI=<name>` | Current shell session only          |
| `-w <name>` on command         | Single command only                 |

---

## Appendix G — Using a Coding Tool as Your LLM Provider

If you already have a **Claude Code** or **Opencode** subscription, you can use it to power Synthadoc's LLM calls — no separate API key required.

### Setup

Open `.synthadoc/config.toml` in your wiki root, comment out the active `default` line, and uncomment the one for your tool:

```toml
[agents]
# default = { provider = "claude-code" }   # no API key — uses your Claude Code subscription
# default = { provider = "opencode" }      # no API key — uses your Opencode subscription
```

The `model` field is optional — if omitted, the tool uses its own configured default. Restart the server after saving.

Ensure the tool is installed and authenticated in your terminal before starting the server. No environment variables are required.

![Switching LLM providers in config.toml — Claude Code enabled](png/synthadoc-switch-provider.png)

> **Web search still needs Tavily.** Even with a CLI provider, `search for:` ingest requires a `TAVILY_API_KEY`. The free tier (1,000 searches/month, no credit card required) is more than enough for typical Synthadoc use — see [Appendix D](#appendix-d--tavily-web-search-key).

> **Note:** CLI providers use BM25 search only — vector/semantic search (`[search] vector = true`) is not supported and will be silently bypassed.

### Demo: ingest + query

Start the server and ingest a source as normal:

```bash
synthadoc serve -w my-wiki
synthadoc ingest "https://example.com/article" -w my-wiki
synthadoc query "What does the article cover?" -w my-wiki
```

The output is identical to a direct API provider. The only difference is that each LLM call is handled by Claude Code or Opencode running as a subprocess.

> **Performance note:** CLI providers add subprocess startup overhead per LLM call. For high-volume batch ingest, a direct API provider (`anthropic`, `gemini`, etc.) is faster.

### Demo: temporary provider override

If your coding tool quota is exhausted and you need to continue ingesting, override the provider for the current server session without editing `config.toml`:

```bash
synthadoc serve -w my-wiki --provider anthropic
```

This uses `ANTHROPIC_API_KEY` (or whichever provider you specify) for that session only. When quota resets, restart without `--provider` to return to the CLI provider.

### Troubleshooting

**"usage quota exhausted" error in job log:**
Your coding tool subscription has hit its usage limit. Options:

1. Wait for quota to reset (typically a few hours)
2. Retry the job: `synthadoc ingest <source> -w my-wiki`
3. Switch temporarily: `synthadoc serve -w my-wiki --provider anthropic`

**"not found in PATH" error on server start:**
Install and authenticate the coding tool first:

- Claude Code: [claude.ai/code](https://claude.ai/code)
- Opencode: [opencode.ai](https://opencode.ai)

---

## Appendix H — BM25 Routing Performance Benchmarks

Measured on Windows 11, Python 3.14, pytest-benchmark 5.2.3 (`time.perf_counter`).
Synthetic wiki with 10 branches; scoped tests search 2 branches (~20% of corpus).
Each result is the median of 5 rounds.

> **What these numbers measure:** The BM25 corpus is built from disk on the first query and then cached in memory for the lifetime of the server process. The reported medians reflect **warm-cache latency** — rounds 2–5 of each benchmark run, where all page content is already in memory. Cold-start latency (the very first query after server start, or immediately after a page write that invalidates the cache) will be higher, proportional to page count and local disk speed. On a running server handling real traffic, warm-cache numbers are representative of typical query latency.

### Scoped search (2 of 10 branches)


| Pages | Median |   Min |   Max |
| ----: | -----: | ----: | ----: |
|   100 |  14 ms |  5 ms | 36 ms |
|   500 |  16 ms |  7 ms | 19 ms |
|  1000 |   9 ms |  8 ms | 12 ms |
| 10000 |  41 ms | 39 ms | 50 ms |

Routing keeps latency nearly flat across corpus sizes — the search is bounded by branch size, not total page count.

### Full-corpus search (no routing)


| Pages | Median |    Min |    Max |
| ----: | -----: | -----: | -----: |
|   100 |   7 ms |   6 ms |  32 ms |
|   500 |  14 ms |  14 ms |  16 ms |
|  1000 |  22 ms |  21 ms |  31 ms |
| 10000 | 191 ms | 184 ms | 210 ms |

Full-corpus BM25 scales roughly linearly with page count. At 10000 pages the median is 191 ms — comfortably within a 500 ms interactive budget.

### Takeaway

For wikis under ~1000 pages the difference between scoped and full-corpus is negligible (both under 25 ms). At 10000 pages routing delivers a **4–5× speedup** (41 ms vs. 191 ms). Enable ROUTING.md ([Step 15](#step-15--set-up-routingmd--scoped-search)) once your wiki exceeds a few hundred pages.
