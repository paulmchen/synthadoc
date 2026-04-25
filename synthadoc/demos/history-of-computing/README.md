# History of Computing — Demo Wiki

A pre-built Synthadoc wiki demonstrating the full ingest lifecycle: clean merges,
source conflicts, and orphan detection — using real PDF, XLSX, and PNG source files.

## Install

**Linux / macOS:**
```bash
synthadoc install history-of-computing --target ~/wikis --demo
```

**Windows (cmd.exe):**
```cmd
synthadoc install history-of-computing --target %USERPROFILE%\wikis --demo
```

**Windows (PowerShell):**
```powershell
synthadoc install history-of-computing --target $env:USERPROFILE\wikis --demo
```

Then open the installed folder as an Obsidian vault. Wiki pages live under `wiki/`.
All commands use the wiki name (`-w history-of-computing`) — no paths needed.

---

## Source documents (pre-built)

Four source documents are included in `raw_sources/` — no generation step needed:

| File | Format | Scenario |
|------|--------|----------|
| `turing-enigma-decryption.pdf` | PDF | **Clean merge** — enriches `alan-turing` |
| `computing-pioneers-timeline.xlsx` | XLSX | **Clean merge** — structured timeline, enriches multiple pages |
| `first-compiler-controversy.pdf` | PDF | **Conflict** — contradicts `grace-hopper` (A-0 vs FORTRAN) |
| `quantum-computing-primer.png` | PNG | **Orphan** — completely new topic, no existing page links to it |

If you want to regenerate them: `python raw_sources/generate_sources.py`

---

## Step 1 — Start the server

The server must be running before any other command (query, ingest, lint) can work.
Open a dedicated terminal and leave it running:

```
synthadoc serve -w history-of-computing
```

Expected output:
```
HTTP API running on http://127.0.0.1:7070
```

Use a second terminal for all commands below.

---

## Free-tier API usage

This demo makes roughly **10–15 LLM calls** across all four scenarios (ingest, query
decomposition, web search, lint auto-resolve). Free-tier Gemini allows **20 requests per
day** — enough for one full run-through, but not multiple sessions in the same day.

**If you hit the daily limit** the server logs `Daily quota exhausted` and immediately
fails pending jobs (no retry loop). You can either wait until midnight UTC for the quota
to reset, or switch providers by editing `.synthadoc/config.toml`:

```toml
# Groq — free tier, generous daily budget
default = { provider = "groq", model = "llama-3.3-70b-versatile" }

# Paid Gemini key — no daily cap
default = { provider = "gemini", model = "gemini-2.5-flash-lite" }
```

Restart `synthadoc serve` after changing the provider.

---

## Step 2 — Scenario A: Clean merge

Ingest the PDF about Turing's Enigma work. It adds new detail to the existing
`alan-turing` page without contradicting anything.

```
synthadoc ingest raw_sources/turing-enigma-decryption.pdf -w history-of-computing
synthadoc jobs status <job-id> -w history-of-computing
```

Then ingest the structured timeline spreadsheet. It enriches several pages at once:

```
synthadoc ingest raw_sources/computing-pioneers-timeline.xlsx -w history-of-computing
synthadoc jobs status <job-id> -w history-of-computing
```

**Expected result:** job status shows `completed`. Open `alan-turing.md` in Obsidian —
it should have new content from the PDF. Check `wiki/index.md` — new pages appear
under `## Recently Added`.

---

## Step 3 — Scenario B: Conflict and resolution

Ingest the controversy PDF. It argues that Hopper's A-0 was a loader, not a compiler —
directly contradicting the existing `grace-hopper` page.

```
synthadoc ingest raw_sources/first-compiler-controversy.pdf -w history-of-computing
synthadoc jobs status <job-id> -w history-of-computing
```

**Expected result:** `grace-hopper.md` frontmatter changes to `status: contradicted`.
In Obsidian, open `wiki/dashboard.md` — the page appears in the **Contradicted pages** table.

Check via CLI:
```
synthadoc lint report -w history-of-computing
```

**Option 1 — Manual resolution:**

1. Open `wiki/grace-hopper.md` in Obsidian
2. Read both positions; edit the content to reflect the nuanced view (Hopper pioneered
   the concept; Backus delivered the first production compiler)
3. Change `status: contradicted` to `status: active` in the frontmatter
4. Save

**Option 2 — Auto-resolve (LLM-assisted):**

```
synthadoc lint run -w history-of-computing --auto-resolve
synthadoc jobs status <job-id> -w history-of-computing
```

The LLM proposes a resolution and appends it to the page. Review the result in Obsidian.

---

## Step 4 — Scenario C: Orphan and human decision

Ingest the quantum computing image. It covers a topic (qubits, Shor's algorithm, Google
Sycamore) not mentioned in any existing wiki page.

```
synthadoc ingest raw_sources/quantum-computing-primer.png -w history-of-computing
synthadoc jobs status <job-id> -w history-of-computing
```

**Expected result:** a new `quantum-computing` (or similar) page is created, but nothing
links to it. Open `wiki/dashboard.md` in Obsidian — it appears in the **Orphan pages**
table.

Check via CLI:
```
synthadoc lint report -w history-of-computing
```

**Your decision — three options:**

1. **Link it** — open a related page (e.g. `artificial-intelligence-history.md`) and add
   `[[quantum-computing]]` in a relevant sentence. The page is no longer an orphan.

2. **Leave it** — keep it as a standalone page until you ingest more quantum content
   that naturally references it.

3. **Delete it** — if the page quality is poor, delete `wiki/quantum-computing.md` and re-ingest
   with `--force` once you have a better source document.

---

## Step 5 — Check status and jobs

```
synthadoc status -w history-of-computing
synthadoc jobs list -w history-of-computing
synthadoc lint report -w history-of-computing
```

---

## Wiki pages (pre-built)

| Page | Description |
|------|-------------|
| `alan-turing` | Biography and theoretical contributions |
| `grace-hopper` | First compiler, COBOL, and debugging |
| `von-neumann-architecture` | Stored-program computer model |
| `transistor-and-microchip` | From Bell Labs transistor to Moore's Law |
| `unix-history` | Origins of Unix and the C language |
| `open-source-movement` | GNU, Linux, and the bazaar model |
| `programming-languages-overview` | Evolution from assembly to modern languages |
| `internet-origins` | ARPANET to the World Wide Web |
| `personal-computer-revolution` | Altair, Apple II, IBM PC, and the GUI |
| `artificial-intelligence-history` | Dartmouth conference to large language models |

---

## Uninstall

```
synthadoc uninstall history-of-computing
```

Requires two confirmations — a y/N prompt and typing the wiki name. There is no `--yes` flag.
