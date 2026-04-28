# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from pathlib import Path

_AGENTS_MD = """# AGENTS.md — {domain} Wiki

## Purpose
This wiki captures knowledge about: {domain}.

## Ingest Guidelines
- Summarize key claims and findings
- Cross-reference related concepts using `[[page-name]]` link syntax
- Flag contradictions with ⚠ markers

## Query Guidelines
- Answer using only wiki content
- Always cite sources using `[[page-name]]` link syntax
"""

_CONFIG_TOML = """\
# synthadoc per-project configuration

[wiki]
domain = "{domain}"

[server]
port = {port}  # change this if running multiple wikis simultaneously

[agents]
default = {{ provider = "gemini", model = "gemini-2.5-flash-lite" }}
# Alternatives (uncomment and restart to switch):
# default = {{ provider = "gemini",    model = "gemini-2.5-flash" }}         # free tier: 10 RPM / 250 RPD
# default = {{ provider = "gemini",    model = "gemini-1.5-flash" }}         # free tier: 15 RPM / 1,500 RPD
# default = {{ provider = "minimax",   model = "MiniMax-M2.5" }}             # paid, cheapest text-only ($0.15/M in)
# default = {{ provider = "groq",      model = "llama-3.3-70b-versatile" }}  # free tier, 100K tokens/day
# default = {{ provider = "anthropic", model = "claude-sonnet-4-6" }}        # paid, highest quality
# default = {{ provider = "deepseek",  model = "deepseek-chat" }}             # paid, very cheap ($0.14/M in); text-only, no vision
# default = {{ provider = "ollama",    model = "llama3.2" }}                  # fully local, no API key
#
# LLM call timeout — useful for reasoning models (e.g. MiniMax-M2.5) that can
# spend 2+ minutes on a single prompt and return an empty response instead of
# raising an error.  Setting this causes synthadoc to fail fast with a clear
# log message so you know to adjust the model or prompt size.
# 0 = no limit (provider default).  Restart the server after changing.
# llm_timeout_seconds = 90

[ingest]
max_pages_per_ingest = 15

[cost]
soft_warn_usd = 0.50
hard_gate_usd = 2.00

[logs]
# Console log level shown in the terminal when running 'synthadoc serve'.
# DEBUG | INFO | WARNING | ERROR  (default: INFO)
level = "INFO"

# Rotating log file settings for .synthadoc/logs/synthadoc.log
# max_file_mb  — size limit per file before rotation (default: 5 MB)
# backup_count — number of rotated files to keep, so total ≈ max_file_mb × backup_count
#                e.g. 5 MB × 5 = ~25 MB maximum on disk
max_file_mb  = 5
backup_count = 5

[search]
vector = false             # set to true to enable semantic re-ranking (downloads ~130 MB model once)
vector_top_candidates = 20
"""

_GITIGNORE = ".synthadoc/\n__pycache__/\n*.pyc\n.env\n"

_PURPOSE_MD = """\
# Wiki Purpose

This wiki covers: {domain}.

Include: topics directly related to {domain}.
Exclude: unrelated domains. When in doubt, ingest and review.
"""

_DASHBOARD_MD = """\
---
title: Dashboard
tags: [dashboard]
status: active
confidence: high
created: '{created}'
sources: []
---

# {domain} — Dashboard

> Requires the **Dataview** community plugin (Settings → Community plugins → Browse → "Dataview").

---

## Contradicted pages — need review

```dataview
TABLE status, confidence, created
FROM "wiki"
WHERE status = "contradicted"
SORT created DESC
```

*These pages were flagged during ingest as conflicting with a newer source.
Open each one, resolve the conflict, then change `status` to `active`.*

---

## Orphan pages — no inbound links

```dataview
TABLE status, created
FROM "wiki"
WHERE orphan = true
SORT created DESC
```

*These pages exist but nothing links to them.
Orphan status is set by `synthadoc lint run` — run it first to populate this list.
Add `[[page-name]]` to a related content page to integrate it into the graph.*

---

## Recently added

```dataview
TABLE status, confidence
FROM "wiki"
WHERE file.name != "index" AND file.name != "dashboard" AND file.name != "purpose"
SORT created DESC
LIMIT 10
```
"""


def init_wiki(root: Path, domain: str = "General", port: int = 7070) -> None:
    from datetime import date
    (root / "wiki").mkdir(parents=True, exist_ok=True)
    (root / "raw_sources").mkdir(exist_ok=True)
    (root / "hooks").mkdir(exist_ok=True)
    (root / ".synthadoc" / "logs").mkdir(parents=True, exist_ok=True)
    (root / ".obsidian").mkdir(exist_ok=True)
    (root / ".obsidian" / "app.json").write_text(
        '{\n  "userIgnoreFilters": [\n    "raw_sources"\n  ]\n}\n',
        encoding="utf-8", newline="\n")
    (root / "AGENTS.md").write_text(
        _AGENTS_MD.format(domain=domain), encoding="utf-8", newline="\n")
    (root / "wiki" / "index.md").write_text(
        "# Index\n\n", encoding="utf-8", newline="\n")
    (root / "wiki" / "purpose.md").write_text(
        _PURPOSE_MD.format(domain=domain), encoding="utf-8", newline="\n")
    (root / "wiki" / "dashboard.md").write_text(
        _DASHBOARD_MD.format(domain=domain, created=date.today().isoformat()),
        encoding="utf-8", newline="\n")
    (root / "log.md").write_text(
        "# Activity Log\n\n", encoding="utf-8", newline="\n")
    (root / ".synthadoc" / "config.toml").write_text(
        _CONFIG_TOML.format(domain=domain, port=port),
        encoding="utf-8", newline="\n")
    (root / ".gitignore").write_text(_GITIGNORE, encoding="utf-8", newline="\n")
