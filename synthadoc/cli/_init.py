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
default = {{ provider = "gemini", model = "gemini-2.0-flash" }}
# Alternatives (uncomment and restart to switch):
# default = {{ provider = "groq",      model = "llama-3.3-70b-versatile" }} # free tier, 100K tokens/day
# default = {{ provider = "anthropic", model = "claude-sonnet-4-6" }}       # paid, highest quality
# default = {{ provider = "ollama",    model = "llama3.2" }}                 # fully local

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
WHERE length(file.inlinks) = 0
AND file.name != "index"
AND file.name != "dashboard"
AND file.name != "purpose"
SORT created DESC
```

*These pages exist but nothing links to them.
Add `[[page-name]]` to a related page or to [[index]].*

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
