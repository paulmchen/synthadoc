# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
"""Synthadoc error code registry.

Every user-facing error carries a short, stable code so that errors can be
searched, documented, and handled programmatically.

Format: <CATEGORY>-<NNN>

Categories
----------
SRV    Server lifecycle errors (not running, port conflict, HTTP errors)
WIKI   Wiki filesystem errors (not found, invalid structure, not writable)
CFG    Configuration / environment errors (missing API key, bad provider)
SKILL  Skill dispatch and execution errors (not found, missing dep, blocked)
INGEST Ingest source errors (file not found, empty, wrong type)
JOB    Job management errors (not found)
"""
from __future__ import annotations

# ── Server ────────────────────────────────────────────────────────────────────
SRV_NOT_RUNNING  = "SRV-001"   # No server listening for the requested wiki
SRV_PORT_IN_USE  = "SRV-002"   # Port already bound by another process
SRV_HTTP_ERROR   = "SRV-003"   # Server returned a 4xx/5xx response
SRV_BG_CRASH     = "SRV-004"   # Background server process exited immediately

# ── Wiki ──────────────────────────────────────────────────────────────────────
WIKI_NOT_FOUND       = "WIKI-001"  # Wiki root directory does not exist
WIKI_INVALID         = "WIKI-002"  # Directory exists but missing wiki/ subfolder
WIKI_NOT_WRITABLE    = "WIKI-003"  # wiki/ directory is not writable
WIKI_ALREADY_EXISTS  = "WIKI-004"  # Install target already exists on disk
WIKI_DEMO_NOT_FOUND  = "WIKI-005"  # Unknown demo template name
WIKI_NOT_REGISTERED  = "WIKI-006"  # Name not in ~/.synthadoc/wikis.json

# ── Config / Environment ──────────────────────────────────────────────────────
CFG_MISSING_API_KEY  = "CFG-001"   # Required env var (API key) not set
CFG_UNKNOWN_PROVIDER = "CFG-002"   # Provider name not recognised

# ── Skills ────────────────────────────────────────────────────────────────────
SKILL_NOT_FOUND   = "SKILL-001"  # No skill matched the source string
SKILL_MISSING_DEP = "SKILL-002"  # Required pip package not installed
SKILL_URL_BLOCKED = "SKILL-003"  # URL returned 403 (bot/paywall protection)
SKILL_WEB_NO_KEY  = "SKILL-004"  # TAVILY_API_KEY not set for web search

# ── Ingest ────────────────────────────────────────────────────────────────────
INGEST_NOT_FOUND  = "INGEST-001"  # Source file or directory not found
INGEST_EMPTY      = "INGEST-002"  # Source file exists but is empty
INGEST_NOT_DIR    = "INGEST-003"  # --batch target exists but is not a directory

# ── Jobs ──────────────────────────────────────────────────────────────────────
JOB_NOT_FOUND = "JOB-001"   # Job ID does not exist in jobs.db


def cli_error(code: str, message: str, hint: str = "") -> None:
    """Print a categorised error and exit with code 1.

    Only call from CLI-layer code. Agents and skills raise standard Python
    exceptions (with the error code embedded in the message string).

    Parameters
    ----------
    code:
        One of the constants defined in this module, e.g. ``SRV_NOT_RUNNING``.
    message:
        Human-readable description of what went wrong.
    hint:
        Optional follow-up text (suggested fix, next step).
    """
    import typer
    lines = [f"\n[{code}] {message}"]
    if hint:
        lines.append(hint)
    lines.append("")
    typer.echo("\n".join(lines), err=True)
    raise typer.Exit(1)
