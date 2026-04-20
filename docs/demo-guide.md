# Synthadoc Demo Guide — History of Computing

**Document version: v0.2.0 (in progress — not yet released)**

---

## Part 1 — Setup

### What is Obsidian?

Obsidian is a free, local-first knowledge management app. Everything is stored as
plain Markdown files on your machine — no cloud account required, no vendor lock-in.
You open a folder on your filesystem as a "vault" and Obsidian gives it a structured UI.

**Key features relevant to Synthadoc:**


| Feature               | What it does                                                                                                                    |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| **Graph view**        | Visualises every`[[wikilink]]` between notes as a live node graph. Orphan pages (no inbound links) appear as isolated dots.     |
| **Properties panel**  | Renders YAML frontmatter (`status`, `confidence`, `tags`, `created`) as a structured sidebar.                                   |
| **Dataview plugin**   | Queries frontmatter across all notes in real time — like a SQL table over your markdown files. Powers the Synthadoc dashboard. |
| **Command palette**   | `Ctrl/Cmd+P` runs any plugin command, including Synthadoc's ingest and query.                                                   |
| **Community plugins** | Extend Obsidian with third-party functionality installed from within the app.                                                   |

Obsidian is free for personal use. Download it from **[obsidian.md](https://obsidian.md)**.

---

### What does Synthadoc add?

Obsidian is a writing and organisation tool — you create and edit notes manually.
Synthadoc is a **compilation engine**: it reads raw source documents (PDFs, spreadsheets,
images, web pages) and uses an LLM to synthesise, cross-reference, and maintain a
structured wiki automatically.

But Synthadoc goes further than compilation. It also **understands your domain** and
configures itself around it — so you spend your time building knowledge, not managing
the tool.

| Without Synthadoc                        | With Synthadoc                                                                         |
| ---------------------------------------- | -------------------------------------------------------------------------------------- |
| You write each note by hand              | LLM synthesises notes from source documents                                            |
| You design the category structure        | Install generates domain-specific index categories, scope rules, and agent guidelines  |
| You manage links between notes           | Cross-references are inserted automatically                                            |
| You notice contradictions manually       | Ingest pipeline flags conflicting content (`status: contradicted`)                     |
| You track orphan pages by eye            | Dashboard and CLI report orphans with fix suggestions                                  |
| Notes are static once written            | Wiki compiles incrementally as new sources arrive                                      |
| You rewrite instructions as domain grows | `synthadoc scaffold` refreshes index, guidelines, and scope from the current wiki state |
| You write a wiki overview by hand        | `overview.md` is regenerated automatically after every ingest                         |

**Domain-aware from day one.** When you create a wiki with `synthadoc install --domain "Machine Learning"`,
the LLM generates a domain-specific index with 5–8 relevant category headings, ingest and query
guidelines tailored to that field, and a scope definition that tells the engine what to include
and what to skip. No manual setup required.

**Self-improving over time.** As your wiki grows, run `synthadoc scaffold -w <wiki>` to
refresh the index structure, agent guidelines, and purpose definition based on what the wiki
has become. Pages already linked from the index are detected automatically and protected —
the scaffold adapts around your existing knowledge, never discards it.

Synthadoc writes into the same Markdown files Obsidian reads. No special format — every
synthadoc wiki page is a valid Obsidian note.

---

### Supported source types & skills

Synthadoc routes every source to the right **skill** — a self-contained folder that knows
how to read one kind of content. Skills are selected by **file extension** or by
**intent phrase** in the source string. No `--skill` flag needed; the engine detects it
automatically.


| Skill        | Triggered by                                                                                       | Notes                                                                                                                                      |
| ------------ | -------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `pdf`        | `.pdf` extension · phrases: `pdf`, `research paper`, `document`                                   | Primary: pypdf. CJK fallback: pdfminer.six                                                                                                 |
| `url`        | `https://` / `http://` prefix · phrases: `fetch url`, `web page`, `website`                       | httpx + BeautifulSoup HTML cleaning                                                                                                        |
| `markdown`   | `.md` / `.txt` extension · phrases: `markdown`, `text file`, `notes`                              | Direct read, no transformation                                                                                                             |
| `docx`       | `.docx` extension · phrases: `word document`, `docx`                                              | python-docx paragraph extraction                                                                                                           |
| `pptx`       | `.pptx` extension · phrases: `powerpoint`, `presentation`, `pptx`                                 | python-pptx; each slide as a titled section; speaker notes included                                                                        |
| `xlsx`       | `.xlsx` / `.csv` extension · phrases: `spreadsheet`, `excel`, `csv`                               | openpyxl + stdlib csv                                                                                                                      |
| `image`      | `.png` `.jpg` `.jpeg` `.webp` `.gif` `.tiff` · phrases: `image`, `screenshot`, `diagram`, `photo` | Base64 → vision LLM                                                                                                                       |
| `web_search` | Intent phrases only:`search for`, `find on the web`, `look up`, `web search`, `browse`             | No file extension — purely intent-driven. Calls Tavily API; fans out top result URLs as individual ingest jobs. Requires`TAVILY_API_KEY`. |

**Custom skills:** drop a folder containing `SKILL.md` + `scripts/main.py` into
`<wiki-root>/skills/` and the engine picks it up on next start — no install or restart
required. A `SKILL.md` carries YAML frontmatter (name, triggers, entry point, dependencies)
plus a human-readable Markdown body for documentation.

---

### Before you start

If you followed the README, you should already have:

- **Demo wiki installed** — `synthadoc install history-of-computing --target ... --demo`
- **LLM API key set** — `GEMINI_API_KEY` (default, free) or `GROQ_API_KEY` / `ANTHROPIC_API_KEY`
- **Engine running** — `synthadoc serve -w history-of-computing`

If any of these are missing, complete [README Steps 4–6](../README.md#step-4--set-your-api-keys) first, then come back here.

> **No API key needed to browse.** The 10 pre-built pages are already in the wiki — you
> can open them in Obsidian and explore Graph view without any key. An API key is only
> required when you ingest new sources or run lint. Web search (Step 9) additionally
> requires `TAVILY_API_KEY` — see [Appendix — Tavily web search key](#appendix--tavily-web-search-key).
>
> Want to use a different LLM provider (e.g. Groq or Anthropic)? See
> [Appendix — Switching LLM providers](#appendix--switching-llm-providers) at the bottom
> of this guide.

---

### Set up Obsidian

**Obsidian must already be installed** — download from **[obsidian.md](https://obsidian.md)** if not.

**Step 1 — Open the vault in Obsidian**

Open Obsidian → **Open folder as vault** → select the installed wiki folder
(e.g. `%USERPROFILE%\wikis\history-of-computing` on Windows, `~/wikis/history-of-computing` on Linux/macOS).

> **Tip — show all file types in the explorer:** By default Obsidian only displays
> file types it natively understands. `.xlsx` and `.pptx` files in `raw_sources/`
> will be hidden. To show them: **Settings → Files and links → Show all file types**
> → toggle **on**. The files are always present on disk and synthadoc
> reads them regardless of this setting — this is purely a display preference.

---

**Step 2 — Install the Dataview community plugin**

Dataview is required for the live dashboard in `wiki/dashboard.md`.

1. **Settings** (gear icon, bottom-left) → **Community plugins** → **Turn on community plugins**
2. Click **Browse** → search `Dataview` → **Install** → **Enable**

> **Dataview cache:** Dataview caches frontmatter and does not always reflect changes
> made externally by Synthadoc — pages may appear missing, stale, or show an old status
> after an ingest or lint run. When the dashboard disagrees with
> `synthadoc lint report`, drop the cache:
> `Ctrl/Cmd+P` → **Dataview: Drop all cached file metadata**, then reopen the dashboard.
> The CLI report reads files directly and is always authoritative.

---

**Step 3 — Install the Synthadoc Obsidian plugin**

The plugin is pre-built (`obsidian-plugin/main.js`) — no build step needed unless you
modify the TypeScript source.

First, change into the `obsidian-plugin/` folder inside your cloned synthadoc repository, then run:

**Windows (cmd.exe):**

```cmd
mkdir "%USERPROFILE%\wikis\history-of-computing\.obsidian\plugins\synthadoc"
copy main.js "%USERPROFILE%\wikis\history-of-computing\.obsidian\plugins\synthadoc\"
copy manifest.json "%USERPROFILE%\wikis\history-of-computing\.obsidian\plugins\synthadoc\"
```

**Linux / macOS:**

```bash
vault=~/wikis/history-of-computing
mkdir -p "$vault/.obsidian/plugins/synthadoc"
cp main.js manifest.json "$vault/.obsidian/plugins/synthadoc/"
```

---

**Step 4 — Restart Obsidian, then enable and configure the plugin**

After copying the files, **fully quit and reopen Obsidian** — the plugin will not appear
until Obsidian is restarted.

1. In Obsidian: **Settings** → **Community plugins** → find **Synthadoc** → toggle **on**
2. Click the gear icon next to the Synthadoc entry
3. Set **Server URL** to `http://127.0.0.1:7070` (change only if you configured a different port)
4. Leave **Raw sources folder** as `raw_sources`
5. Close settings

---

## Part 2 — Demo Walkthrough

> **Before starting:** the demo wiki must be installed, the engine must be running, and
> Obsidian must be open with the Dataview and Synthadoc plugins enabled (Part 1 above).

### Vault orientation

- Wiki pages are in the `wiki/` subfolder
- `AGENTS.md` and `log.md` are at the vault root — outside `wiki/` so they do not
  appear as nodes in Graph view
- Open `wiki/dashboard.md` to see the live Dataview tables (requires the Dataview plugin)

In **Graph view** (`Ctrl/Cmd+G`) you should see 10 interconnected nodes. The `index` and
`dashboard` nodes connect to everything; topic pages cluster by cross-links.

The server should already be running from README Step 6. If the Obsidian plugin shows a
connection error, check the server is up:

```
synthadoc status -w history-of-computing
```

or probe the health endpoint directly:

```
curl http://127.0.0.1:7070/health
```

If neither responds, start the server:

```
synthadoc serve -w history-of-computing --background
```

![synthadoc serve startup](synthadoc-serve.png)

The banner confirms the port, wiki path, and PID. If you see
`Warning: TAVILY_API_KEY is not set`, web search jobs will not work — see
[Appendix — Tavily web search key](#appendix--tavily-web-search-key) if you plan to use Step 9.

> **Obsidian ribbon:** The ribbon is the narrow vertical icon strip on the far left edge of
> the Obsidian window. Once the Synthadoc plugin is enabled, the Synthadoc book icon
> (![ribbon icon](synthadoc-ribbon-icon.png)) appears there. It may be near the bottom if
> other plugins have added icons above it — hover to find the one with the **"Synthadoc
> status"** tooltip. Clicking it shows the live wiki page count. This is a convenience
> shortcut; all Synthadoc functionality is also available via the command palette (`Ctrl/Cmd+P`).

**Plugin commands available from this point on** (`Ctrl/Cmd+P` in Obsidian, type `Synthadoc` to filter):

For the full command reference including syntax, descriptions, and what each command does, see [Appendix A — Obsidian Plugin Command Reference](#appendix-a--obsidian-plugin-command-reference).

---

### Step 1 — Query the pre-built wiki

Before ingesting anything, verify the pre-built content is queryable:

```
synthadoc query "How did Alan Turing influence modern computers?" -w history-of-computing
synthadoc query "What is Moore's Law and why does it matter?" -w history-of-computing
synthadoc query "How did Unix influence the open source movement?" -w history-of-computing
```

Each answer cites `[[wikilinks]]` pointing to the source pages.

#### Compound and multi-part queries

Synthadoc automatically decomposes complex questions into focused sub-queries,
retrieves pages for each part independently, then synthesises a single answer:

```
# Two-part question — retrieves pages for each part separately
synthadoc query "Who invented FORTRAN and what influence did it have on later languages?" -w history-of-computing

# Comparative — fetches two independent topics in parallel
synthadoc query "Compare Alan Turing's theoretical contributions with Von Neumann's architectural contributions." -w history-of-computing

# Causal / multi-hop
synthadoc query "How did Moore's Law shape both hardware design and software expectations over time?" -w history-of-computing
```

Simple questions produce a single sub-question — behaviour is identical to before.

#### What happens inside a compound query

```
Question:  "Who invented FORTRAN and what was the Bombe machine?"

Server log:
  query decomposed into 2 sub-question(s):
    "Who invented FORTRAN?" | "What was the Bombe machine?"

Pipeline:
  → BM25 search for "Who invented FORTRAN?"       (parallel)
  → BM25 search for "What was the Bombe machine?" (parallel)
  → merge results — best score per page wins
  → LLM synthesises a single answer citing both sets of pages
```

Simple single-topic questions decompose to 1 sub-question — behaviour identical to v0.1, no extra LLM call overhead.

You can also query from Obsidian: open the command palette (`Ctrl/Cmd+P`) →
`Synthadoc: Query wiki...` → type your question → press **Ask**.

![Synthadoc query result in Obsidian](synthadoc-query-result.png)

---

### Step 2 — Batch ingest all demo sources

The five source files are pre-built in `raw_sources/`:


| File                               | Skill                      | Scenario                                                                                                                                                                      |
| ---------------------------------- | -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `turing-enigma-decryption.pdf`     | `pdf` (`.pdf` extension)   | **A — Clean merge**: enriches `alan-turing`                                                                                                                                  |
| `computing-pioneers-timeline.xlsx` | `xlsx` (`.xlsx` extension) | **A — Clean merge**: structured timeline, enriches multiple pages                                                                                                            |
| `cs-milestones-overview.pptx`      | `pptx` (`.pptx` extension) | **A — Clean merge + new pages**: 6-slide deck; enriches `ada-lovelace`, `alan-turing`, `grace-hopper`; creates new pages for ENIAC, transistor history, and internet origins |
| `first-compiler-controversy.pdf`   | `pdf` (`.pdf` extension)   | **B — Conflict**: contradicts `grace-hopper`                                                                                                                                 |
| `quantum-computing-primer.png`     | `image` (`.png` extension) | **C — Orphan**: brand new topic, no existing page links to it                                                                                                                |

**Via CLI** using `--batch`:

```
synthadoc ingest --batch raw_sources/ -w history-of-computing
```

**Via Obsidian plugin**: command palette (`Ctrl/Cmd+P`) → `Synthadoc: Ingest all sources`.

Both methods enqueue one job per file. Watch all jobs at once:

```
synthadoc jobs list -w history-of-computing
```

![synthadoc jobs list output](synthadoc-jobs-list.png)

Wait until all five show `completed`. Filter by status:

```
synthadoc jobs list --status pending -w history-of-computing
synthadoc jobs list --status completed -w history-of-computing
```

Or from Obsidian: command palette → `Synthadoc: List jobs...` → use the filter dropdown.

![Synthadoc jobs modal in Obsidian](synthadoc-jobs-modal.png)

Once all jobs complete, open **Graph view** (`Ctrl/Cmd+G`) in Obsidian to see the expanded wiki — new nodes for the ingested topics will have appeared and linked into the existing graph:

![Obsidian graph view after batch ingest](synthadoc-graph-view.png)

---

### Step 3 — Scenario A: Clean merge

Refresh Obsidian after the first three jobs complete.

**`turing-enigma-decryption.pdf`** — open `wiki/alan-turing.md`. New content about
Bletchley Park, the Bombe machine, and Turing's posthumous recognition has been merged
into the existing page without contradiction.

**`computing-pioneers-timeline.xlsx`** — the structured two-sheet workbook (timeline +
people reference) enriches several pages with new content appended to existing pages.

**`cs-milestones-overview.pptx`** — the 6-slide PowerPoint deck is processed slide by
slide. Each slide becomes a titled section in the extracted text. Open the ingest log to
see how the engine mapped slide content to wiki pages:

```
synthadoc audit history -w history-of-computing
```

![synthadoc audit history output](synthadoc-audit-history.png)

Expected pages touched or created:


| Wiki page                              | What changed                                                          |
| -------------------------------------- | --------------------------------------------------------------------- |
| `ada-lovelace.md`                      | Enriched with the 1843 Bernoulli-number algorithm detail from Slide 2 |
| `alan-turing.md`                       | ENIAC context from Slide 3 merged alongside existing Turing content   |
| `grace-hopper.md`                      | The ENIAC Six detail from Slide 3 merged in                           |
| `eniac.md` _(new)_                     | Created from Slide 3 — ENIAC weight, speed, and the six programmers  |
| `transistor-and-moores-law.md` _(new)_ | Created from Slide 4 — Bell Labs, Shockley, Moore's Law              |
| `internet-history.md` _(new)_          | Created from Slide 5 — ARPANET, TCP/IP Flag Day                      |

The speaker notes on each slide are extracted and included in the synthesis context,
giving the LLM extra background without cluttering the final wiki page.

You can also ingest the deck in one shot via CLI:

```
synthadoc ingest raw_sources/cs-milestones-overview.pptx -w history-of-computing
```

Verify with queries that use the new content:

```
synthadoc query "What was the Bombe machine and who built it?" -w history-of-computing
synthadoc query "Who invented FORTRAN and when?" -w history-of-computing
synthadoc query "When did the modern internet begin?" -w history-of-computing
synthadoc query "What was the Bombe machine, and how did it contribute to the Allied victory in WWII?" -w history-of-computing
```

#### When a query returns a thin answer

If the wiki doesn't cover a topic yet, Synthadoc detects the gap automatically and suggests web searches:

```
> [!tip] Knowledge Gap Detected
> Your wiki doesn't have enough on this topic yet. Enrich it with a web search:
>
> **From Obsidian:** Open Command Palette (`Cmd+P` / `Ctrl+P`) → **Synthadoc: Ingest: web search**
>
> **From the terminal:**
> ```bash
> synthadoc ingest "search for: Enigma machine cryptography WWII" -w history-of-computing
> synthadoc ingest "search for: Alan Turing Bombe machine design" -w history-of-computing
> ```
>
> After ingesting, re-run your query to get a richer answer.
```

The gap is triggered when fewer than 3 pages are retrieved OR the best BM25 match scores below the configured threshold (`gap_score_threshold = 2.0` in `.synthadoc/config.toml`). The suggested search strings are generated automatically by `SearchDecomposeAgent`.

---

### Step 4 — Scenario B: Conflict detection and resolution

After `first-compiler-controversy.pdf` is processed, open `wiki/grace-hopper.md`.
The frontmatter will show:

```yaml
status: contradicted
```

The PDF argues Hopper's A-0 was a loader, not a compiler, and that FORTRAN (1957)
deserves the "first compiler" title — contradicting the existing page.

**Check via CLI:**

```
synthadoc lint report -w history-of-computing
```

```
Contradicted pages (1) - need review:

  grace-hopper
    -> Open wiki/grace-hopper.md, resolve the conflict, then set status: active
    -> Or re-run: synthadoc lint run -w history-of-computing --auto-resolve
```

**In Obsidian:** open `wiki/dashboard.md` — `grace-hopper` appears in the
**Contradicted pages** table. The Properties panel shows `status: contradicted`.

**Option 1 — Manual resolution:**

1. Open `wiki/grace-hopper.md` in Obsidian
2. Edit the content to reflect a nuanced view — Hopper pioneered automated code
   generation with A-0; Backus and IBM delivered the first production compiler with
   FORTRAN in 1957
3. Change `status: contradicted` → `status: active` in the Properties panel or frontmatter
4. Save — the Contradicted pages table in `dashboard.md` clears immediately

**Option 2 — LLM auto-resolve:**

```
synthadoc lint run -w history-of-computing --auto-resolve
synthadoc jobs status <job-id> -w history-of-computing
```

The LLM proposes a resolution, appends it as a `**Resolution:**` block, and sets
`status: active`. Review the result in Obsidian and edit if needed.

> **Dashboard still showing the contradiction?** Dataview may be serving stale cached
> metadata. Drop the cache: `Ctrl/Cmd+P` → **Dataview: Drop all cached file metadata**.
> If `synthadoc lint report -w history-of-computing` shows "all clear", the file on disk
> is already correct — Dataview just hasn't caught up yet.

---

### Step 5 — Scenario C: Orphan detection and human decision

After `quantum-computing-primer.png` is processed, a new wiki page is created (e.g.
`wiki/quantum-computing.md`). No existing page links to it — it is an orphan.

**Check via CLI:**

```
synthadoc lint report -w history-of-computing
```

```
Orphan pages (2) - no inbound links:

  ada-lovelace
    -> Add [[ada-lovelace]] to a related page, or add to wiki/index.md:
         - [[ada-lovelace]] — computer science history, programming languages, open-source movement, artificial intelligence
  quantum-computing
    -> Add [[quantum-computing]] to a related page, or add to wiki/index.md:
         - [[quantum-computing]] — quantum computing, qubits, Shor's algorithm, Grover's algorithm
```

**In Obsidian:** open `wiki/dashboard.md` — the new page should appear in the **Orphan pages**
table. In Graph view it may still appear connected if the page contains outbound
`[[wikilinks]]` to other pages — Obsidian draws edges in both directions. Synthadoc
defines an orphan as a page with no **inbound** links: no other page references it. The
dashboard and lint report are the reliable way to identify orphans.

> **Orphan count not matching the CLI?** Dataview may not have indexed the newly created
> pages yet. Drop the cache: `Ctrl/Cmd+P` → **Dataview: Drop all cached file metadata**,
> then reopen `dashboard.md`. Use `synthadoc lint report -w history-of-computing` as the
> authoritative count — it reads files directly with no cache.

**Three options:**

**Option 1 — Link it (recommended):**
Open `wiki/artificial-intelligence-history.md` and add a sentence such as:

```
Quantum hardware such as [[quantum-computing]] may dramatically accelerate future AI workloads.
```

Save. The page is no longer an orphan and disappears from the dashboard table.

**Option 2 — Add to index:**
The lint report prints a ready-to-paste suggested entry — copy it, open `wiki/index.md`,
add a section heading if needed, and paste. Edit the description to your liking:

```markdown
## Platforms and AI
- [[quantum-computing]] — quantum-computing, hardware, algorithms
```

**Option 3 — Delete and re-ingest:**
If the extracted content quality is poor, delete `wiki/quantum-computing.md` from Obsidian
and re-ingest with a better source document later:

```
synthadoc ingest raw_sources/quantum-computing-primer.png --force -w history-of-computing
```

---

### Step 6 — Run a full lint pass

After resolving the conflict and orphan, confirm everything is clean:

```
synthadoc lint run -w history-of-computing
synthadoc jobs status <job-id> -w history-of-computing
synthadoc lint report -w history-of-computing
```

Expected output when all issues are resolved:

```
All clear — no contradictions or orphan pages found.
```

---

### Step 7 — Check overall status

```
synthadoc status -w history-of-computing
synthadoc jobs list -w history-of-computing
```

After the full demo the page count should be 12 or more (10 pre-built + newly ingested
pages). `synthadoc status` shows page count, pending jobs, and total jobs.

---

### Step 8 — Single-file ingest

The demo used batch ingest. You can also ingest one file at a time:

**Windows (cmd):**

```cmd
(echo # Ada Lovelace & echo Ada Lovelace (1815-1852) is widely regarded as the first computer programmer. & echo She worked with Charles Babbage on his Analytical Engine and wrote the first & echo algorithm intended to be processed by a machine.) > %USERPROFILE%\wikis\history-of-computing\raw_sources\ada-lovelace.txt

synthadoc ingest raw_sources/ada-lovelace.txt -w history-of-computing
```

**Linux / macOS:**

```bash
cat > ~/wikis/history-of-computing/raw_sources/ada-lovelace.txt << 'EOF'
# Ada Lovelace
Ada Lovelace (1815-1852) is widely regarded as the first computer programmer.
She worked with Charles Babbage on his Analytical Engine and wrote the first
algorithm intended to be processed by a machine.
EOF

synthadoc ingest raw_sources/ada-lovelace.txt -w history-of-computing
```

The new page is created as an orphan — check `wiki/dashboard.md` or run
`synthadoc lint report -w history-of-computing` to see it, then link or index it.

You can also ingest from Obsidian: open any note → command palette (`Ctrl/Cmd+P`) →
`Synthadoc: Ingest current file as source`.

---

### Step 9 — Web search ingestion

> **Requires:** `TAVILY_API_KEY` — see [Appendix — Tavily web search key](#tavily-web-search-key).

The `web_search` skill is fully live in v0.1. Unlike every other skill, it has **no file extension** — it is selected by recognising an intent phrase in the source string. The engine calls the Tavily search API, gets the top result URLs (up to 20), and enqueues each URL as a separate ingest job. Pages are created for each result that passes scope filtering.

**Trigger phrases** (any of these in the source string activates the skill):


| Phrase            | Example source string                                    |
| ----------------- | -------------------------------------------------------- |
| `search for`      | `"search for: Dennis Ritchie C language Bell Labs"`      |
| `find on the web` | `"find on the web: Linus Torvalds Linux creation story"` |
| `look up`         | `"look up Ada Lovelace Analytical Engine contributions"` |
| `web search`      | `"web search ENIAC first electronic computer 1945"`      |
| `browse`          | `"browse recent articles on quantum error correction"`   |

**Example — enrich the history-of-computing wiki via web search:**

```
synthadoc ingest "search for: Dennis Ritchie C programming language Bell Labs history" -w history-of-computing
synthadoc ingest "find on the web: Linus Torvalds Linux kernel creation 1991" -w history-of-computing
synthadoc ingest "search for: ENIAC first general purpose electronic computer history" -w history-of-computing
```

Each command fans out to up to 20 URL ingest jobs. Watch them process:

```
synthadoc jobs list -w history-of-computing
```

Pages such as `dennis-ritchie`, `linux-kernel-history`, and `eniac` will be created or enriched. The `wiki/overview.md` page is regenerated automatically after each batch completes.

#### What happens inside a web search

When you run `synthadoc ingest "search for: ..."`, Synthadoc automatically decomposes your topic before hitting the web:

```
Input:  "search for: yard gardening in Canadian climate zones"

Server log:
  web search decomposed into 3 queries:
    "Canada hardiness zones map" | "frost dates Canadian cities" | "planting guide by province Canada"

Result:
  3 parallel Tavily searches → URLs deduplicated across all results → fan-out to ~60 page ingest jobs
  (vs ~20 from a single broad search)
```

The decomposition uses a keyword-oriented LLM prompt — separate from query decomposition — because
search engines respond better to terse keyword strings than natural-language questions.

If the LLM decompose call fails for any reason, Synthadoc falls back to your original phrase as a
single search query — ingest always completes.

**Batch web search using a manifest file:**

Create `raw_sources/web-searches.txt`:

```
search for: Dennis Ritchie C programming language Bell Labs history
find on the web: Linus Torvalds Linux kernel creation 1991
search for: Ada Lovelace first computer programmer analytical engine
look up: history of ARPANET and internet origins
search for: John von Neumann stored-program computer architecture
```

Then ingest the whole file at once:

```
synthadoc ingest --file raw_sources/web-searches.txt -w history-of-computing
```

**Preview before committing** — use `--analyse-only` to see how a source will be interpreted without writing pages:

```
synthadoc ingest "search for: quantum computing IBM Google" --analyse-only -w history-of-computing
# → {"entities": ["IBM", "Google", "quantum computing"], "tags": [...], "summary": "..."}
```

**Via Obsidian plugin — dedicated web search modal:**

1. Open the command palette (`Ctrl+P` / `Cmd+P`)
2. Run **Synthadoc: Web search...**
3. Type a topic — e.g. `Linus Torvalds Linux kernel creation 1991`
4. Press **Enter** or click **Search**
5. You'll see: `Queued — job abc123. Pages will appear in your wiki as results are ingested.`
6. Switch to the **Synthadoc: List jobs...** modal to watch the fan-out jobs complete

The modal prepends `search for:` automatically — just type the topic, no prefix needed.

---

### Step 10 — Audit commands

The `synthadoc audit` commands query the append-only `audit.db` without needing `sqlite3`. Use them to review what was ingested, what questions were asked, how much it all cost, and what events occurred.

**Ingest history** — last 20 source records:

```
synthadoc audit history -w history-of-computing
```

![synthadoc audit history output](synthadoc-audit-history.png)

**Cost summary** — token spend for the last 30 days:

```
synthadoc audit cost -w history-of-computing
```

Expected output:

```
Period: last 30 days
Total tokens : 20,080
Total cost   : $0.129
Sources processed: 4
Avg cost/source  : $0.032
```

Pass `--days 7` for a weekly view.

**Query history** — questions asked, sub-question counts, and per-query costs:

```
synthadoc audit queries -w history-of-computing
```

Query history is especially useful after running compound queries — you can see how many sub-questions each query was decomposed into and what it cost.

Pass `--json` for machine-readable output, `-n N` to limit the number of records.

**Audit events** — contradiction detections, auto-resolutions, cost gate triggers:

```
synthadoc audit events -w history-of-computing
```

Expected output:

```
2026-04-11 14:35  contradiction_found   grace-hopper ← first-compiler-controversy.pdf
2026-04-11 14:37  auto_resolved         grace-hopper (confidence: 0.91)
```

These commands replace the need to run raw `sqlite3` queries and are safe to run while the server is active.

---

### Step 11 — Hook: auto-commit wiki to git

Hooks let you trigger shell scripts on lifecycle events. This step wires up
`git-auto-commit.py` so every successful ingest produces a git commit
— giving the wiki automatic version history with descriptive commit messages.

#### One-time setup

**1. Initialise a git repo in the wiki root** (skip if already done):

```bash
cd $(synthadoc status | grep Path | awk '{print $2}')
git init
git add .
git commit -m "init: initial wiki snapshot"
```

**2. Copy the hook script from the library:**

```bash
cp /path/to/synthadoc/repo/hooks/git-auto-commit.py .
```

**3. Add to `.synthadoc/config.toml`:**

```toml
[hooks]
on_ingest_complete = "python git-auto-commit.py"
```

**4. Restart the server** to pick up the config change:

```bash
synthadoc serve -w history-of-computing
```

#### Run it

Drop a new file into `raw_sources/` and ingest it:

**Windows (cmd):**

```cmd
echo Ada Lovelace (1815-1852) is widely regarded as the first computer programmer. > %USERPROFILE%\wikis\history-of-computing\raw_sources\ada-lovelace.txt
```

**Linux / macOS:**

```bash
echo "Ada Lovelace (1815-1852) is widely regarded as the first computer programmer." \
  > ~/wikis/history-of-computing/raw_sources/ada-lovelace.txt
```

Then ingest it:

```
synthadoc ingest raw_sources/ada-lovelace.txt -w history-of-computing
```

#### Verify

```bash
git log --oneline -5
```

Expected output:

```
a3f1b2c wiki: ingest ada-lovelace.txt → created ada-lovelace
d9e4c81 wiki: ingest turing-award.pdf → updated alan-turing; created turing-award
...
```

Each commit message names the source file and lists which pages were created
or updated. Open the wiki in Obsidian — `git log` is the full audit trail of
how the wiki evolved over time.

> **More hooks:** see [`hooks/README.md`](../hooks/README.md) in the repository
> for the full library and contribution guidelines.

---

### Step 12 — Scheduler: nightly auto-ingest

Hooks react to events that already happened. The scheduler goes the other
direction — it proactively triggers operations on a timer, so the wiki
stays fresh without any manual intervention.

**Use case:** as you drop new PDFs, articles, or notes into `raw_sources/`
during the day, a nightly ingest job picks them all up automatically overnight.

#### Register a nightly ingest

```bash
synthadoc schedule add \
  --op "ingest --batch raw_sources/" \
  --cron "0 2 * * *" \
  -w history-of-computing
```

Expected output:

```
Scheduled: sched-a3f1b2c4
```

Synthadoc registers the job directly with the OS scheduler — `crontab` on
macOS/Linux, Task Scheduler (`schtasks`) on Windows. No background daemon
is needed; the OS owns the timer.

#### Verify it was registered

```bash
synthadoc schedule list -w history-of-computing
```

Expected output:

```
sched-a3f1b2c4  0 2 * * *  ingest --batch raw_sources/ -w history-of-computing
```

#### Add a weekly lint pass

```bash
synthadoc schedule add \
  --op "lint run" \
  --cron "0 3 * * 0" \
  -w history-of-computing
```

This registers a Sunday 3 am lint run — contradictions and orphans caught
every week automatically.

```bash
synthadoc schedule list -w history-of-computing
```

Expected output:

```
sched-a3f1b2c4  0 2 * * *  ingest --batch raw_sources/ -w history-of-computing
sched-b7e9d012  0 3 * * 0  lint run -w history-of-computing
```

#### Clean up (demo only)

Remove the scheduled jobs so they do not run after the demo:

```bash
synthadoc schedule remove sched-a3f1b2c4 -w history-of-computing
synthadoc schedule remove sched-b7e9d012 -w history-of-computing
```

> **Note:** the server must be running when a scheduled job fires. For
> production use, run `synthadoc serve` as a background service (systemd,
> launchd, or Windows Service) so it is always available when the OS
> triggers the schedule.

---

### Step 13 — Uninstall

> **Stop the server first.** The serve process must be stopped before uninstalling,
> otherwise the wiki directory will be locked or partially deleted on some systems.

If the server is running in the background, stop it using the PID printed at startup
(also saved in `<wiki-root>/.synthadoc/server.pid`):

```bash
# Linux / macOS
kill $(cat ~/wikis/history-of-computing/.synthadoc/server.pid)

# Windows (cmd)
for /f %p in (%USERPROFILE%\wikis\history-of-computing\.synthadoc\server.pid) do taskkill /PID %p /F
```

Then uninstall:

```
synthadoc uninstall history-of-computing
```

Two confirmations required:

1. `y` to confirm deletion
2. Type `history-of-computing` to confirm the name

The directory and registry entry are both removed. There is no `--yes` flag — this is intentional.

---

## Appendix — Switching LLM providers

Synthadoc supports five LLM providers and defaults to **Gemini Flash** — free, no credit
card, and 1 million tokens per day. You can switch at any time by editing
`<wiki-root>/.synthadoc/config.toml` and restarting the server. The wiki, cache, and
audit trail are provider-agnostic — switching never requires re-ingesting anything.

| Provider    | Key env var         | Free tier                  |
| ----------- | ------------------- | -------------------------- |
| `gemini`    | `GEMINI_API_KEY`    | **Yes — default** · 15 RPM / 1M tokens per day              |
| `groq`      | `GROQ_API_KEY`      | Yes — fast Llama models, 100K tokens/day                    |
| `ollama`    | _(none)_            | Yes — fully local, no rate limits                           |
| `anthropic` | `ANTHROPIC_API_KEY` | No — pay-per-token, highest quality                         |
| `openai`    | `OPENAI_API_KEY`    | No — pay-per-token                                          |

> **Hit a quota limit?** Gemini free tier enforces a 15 RPM per-minute cap that can be
> exhausted during a long ingest session. If you see a `429 RateLimitError`, either wait
> a minute and retry, or switch to Groq (Option C below) as a fallback.

### Option A — Anthropic (Claude)

Get a key at **console.anthropic.com** — pay-per-token, no free tier.

**Windows (cmd — current session only):**

```cmd
set ANTHROPIC_API_KEY=sk-ant-your-key-here
```

**Windows (cmd — permanent, survives reboot):**

```cmd
setx ANTHROPIC_API_KEY sk-ant-your-key-here
```

> After `setx`, open a new cmd window for the variable to take effect.

**Linux / macOS:**

```bash
export ANTHROPIC_API_KEY="sk-ant-your-key-here"
```

3. Update the wiki config:

Open `<wiki-root>/.synthadoc/config.toml` and set:

```toml
[agents]
default = { provider = "anthropic", model = "claude-sonnet-4-6" }
```

Restart `synthadoc serve`. The banner will confirm `LLM: anthropic/claude-sonnet-4-6`.

### Option B — Google Gemini (free tier, default)

1. Go to **aistudio.google.com/app/apikey** → create a key (free, no credit card)
2. Set the key:

**Windows (cmd.exe):**

```cmd
set GEMINI_API_KEY=your-gemini-key-here
```

**Linux / macOS:**

```bash
export GEMINI_API_KEY="your-gemini-key-here"
```

3. Update the wiki config to use Gemini:

Open `<wiki-root>/.synthadoc/config.toml` and set:

```toml
[agents]
default = { provider = "gemini", model = "gemini-2.0-flash" }
```

Restart `synthadoc serve` to pick up the change.

> **Gemini free tier limits:** 15 requests per minute and 1 million input tokens per day.
> A long batch ingest can exhaust the per-minute cap — if you see a `429` error, wait
> 60 seconds and retry. For higher burst throughput, switch to Groq (Option C).

### Option C — Groq (free tier, fast inference)

Groq offers free API access to Llama 3 models with fast inference speeds — a good
fallback when Gemini's per-minute rate limit is exhausted.

1. Go to **console.groq.com** → sign up (no credit card needed) → **API Keys** → create a key
2. Set the key:

**Windows (cmd.exe — current session):**

```cmd
set GROQ_API_KEY=gsk_your-key-here
```

**Windows (cmd.exe — permanent, survives reboot):**

```cmd
setx GROQ_API_KEY gsk_your-key-here
```

> After `setx`, open a new cmd window for the variable to take effect.

**Linux / macOS:**

```bash
export GROQ_API_KEY="gsk_your-key-here"
```

3. Update the wiki config:

Open `<wiki-root>/.synthadoc/config.toml` and set:

```toml
[agents]
default = { provider = "groq", model = "llama-3.3-70b-versatile" }
```

Restart `synthadoc serve`. The banner will confirm `LLM: groq/llama-3.3-70b-versatile`.

> **Groq free tier limits:** 100,000 tokens per day for `llama-3.3-70b-versatile`. A
> web search ingest fans out to ~20 URLs, each costing ~1,200 tokens — four web searches
> can exhaust the daily quota. For heavier sustained use, switch back to Gemini (1M
> tokens/day). The server backs off automatically when the quota is hit.

---

## Appendix — Tavily web search key

Web search ingestion (Step 9) requires a Tavily API key. Get a free key at
**tavily.com** (1,000 searches/month, no credit card required).

**Windows (cmd.exe):**

```cmd
set TAVILY_API_KEY=tvly-your-key-here
```

**Linux / macOS:**

```bash
export TAVILY_API_KEY="tvly-your-key-here"
```

If this key is not set, the server starts normally but web search jobs will fail with
`[ERR-SKILL-004]`. All other features work without it.

---

## Appendix A — Obsidian Plugin Command Reference

All commands are accessible via the Command Palette (`Ctrl/Cmd+P`). Type **Synthadoc** to filter.
Commands are grouped by prefix for easy navigation.

### Ingest

| Obsidian command | Brief description | What it does |
|------------------|------------------|--------------|
| `Synthadoc: Ingest: current file` | Ingest the active note | Ingests the currently open note as a source. If no file is open, shows a file picker filtered to the configured raw sources folder. |
| `Synthadoc: Ingest: all sources in folder` | Batch-ingest raw sources folder | Scans the `raw_sources` folder and queues every supported file (md, txt, pdf, docx, xlsx, csv, images) for ingestion. |
| `Synthadoc: Ingest: from URL...` | Ingest a web page by URL | Opens a modal — paste any URL and queue it for fetch and ingestion. |
| `Synthadoc: Ingest: web search...` | Search the web and ingest results | Prompt for a topic; Synthadoc decomposes it into focused keyword sub-queries, fires parallel Tavily searches, deduplicates URLs, and ingests each as a separate wiki page. `Ctrl/Cmd+Enter` to submit. |

### Query

| Obsidian command | Brief description | What it does |
|------------------|------------------|--------------|
| `Synthadoc: Query: ask the wiki...` | Ask the wiki a question | Opens a query panel — ask a natural language question and get a markdown answer with clickable `[[wikilinks]]` to source pages. `Ctrl/Cmd+Enter` to submit. |

### Lint

| Obsidian command | Brief description | What it does |
|------------------|------------------|--------------|
| `Synthadoc: Lint: run` | Run lint silently | Runs lint in the background. A notification shows contradiction and orphan counts when complete. |
| `Synthadoc: Lint: run with auto-resolve` | Run lint and auto-fix contradictions | Same as above but automatically resolves contradictions above the 80% confidence threshold. |
| `Synthadoc: Lint: report` | View full lint report | Opens a report listing all contradicted pages (requiring manual resolution) and orphan pages (no inbound links) with suggested index entries. |

### Jobs

| Obsidian command | Brief description | What it does |
|------------------|------------------|--------------|
| `Synthadoc: Jobs: list...` | View all jobs | Opens a job table showing all ingest/lint/scaffold operations with status, source, and timestamps. Filterable by status: `pending`, `in_progress`, `completed`, `failed`, `skipped`, `dead`. |
| `Synthadoc: Jobs: retry dead job...` | Retry a failed job | Lists all dead jobs and provides a Retry button per job to re-queue it with a fresh retry counter. |
| `Synthadoc: Jobs: purge old completed/dead...` | Clean up old job history | Removes completed and dead jobs older than a specified number of days (default: 7). |

### Wiki

| Obsidian command | Brief description | What it does |
|------------------|------------------|--------------|
| `Synthadoc: Wiki: regenerate scaffold...` | Rebuild wiki structure files | Rewrites `index.md`, `AGENTS.md`, and `purpose.md` for the wiki's domain using the LLM. All existing wiki pages are preserved. |

### Audit

| Obsidian command | Brief description | What it does |
|------------------|------------------|--------------|
| `Synthadoc: Audit: ingest history...` | View ingest history | Shows a table of the last N ingest records — source file, wiki page created/updated, token count, cost, and timestamp. |
| `Synthadoc: Audit: cost summary...` | View LLM cost breakdown | Shows total tokens and USD cost for the last N days with a daily breakdown. |
| `Synthadoc: Audit: query history...` | View recent query history | Shows a table of recent questions asked, sub-question counts, token usage, and cost per query. |

### Ribbon icon

| Obsidian command | Brief description | What it does |
|------------------|------------------|--------------|
| Book icon (left ribbon) | Quick server status | Shows a notice with server online/offline status and current wiki page count. |
