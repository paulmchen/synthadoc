# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
"""Central logging configuration for the synthadoc server.

Call ``setup_logging(wiki_root, cfg)`` once at server startup.  All modules
that use ``logging.getLogger(__name__)`` will automatically inherit the handlers
configured here — no per-module setup needed.

Handler stack
-------------
Console handler
    Level  : cfg.logs.level  (INFO by default, overrideable in config.toml or --verbose)
    Format : human-readable  "HH:MM:SS LEVEL  logger — message"
    Target : stderr

File handler
    Level  : DEBUG always (captures full detail for post-mortem debugging)
    Format : JSON lines — one record per line, machine-parseable
    Target : <wiki-root>/.synthadoc/logs/synthadoc.log
    Rotation: cfg.logs.max_file_mb MB max per file, cfg.logs.backup_count backup files kept

Root logger
    Level  : DEBUG — lets each handler decide what to show/store.
    Third-party noise (httpx, uvicorn access, aiosqlite, asyncio) is suppressed to WARNING.

Configuration (in .synthadoc/config.toml)
------------------------------------------
    [logs]
    level        = "INFO"   # console level: DEBUG | INFO | WARNING | ERROR
    max_file_mb  = 5        # max size per log file before rotation
    backup_count = 5        # number of rotated files to keep
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from synthadoc.config import LogsConfig


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

class _ConsoleFormatter(logging.Formatter):
    """Colourless, human-readable single-line format for the terminal."""

    _LEVEL_ABBREV = {
        logging.DEBUG:    "DEBUG",
        logging.INFO:     "INFO ",
        logging.WARNING:  "WARN ",
        logging.ERROR:    "ERROR",
        logging.CRITICAL: "CRIT ",
    }

    def format(self, record: logging.LogRecord) -> str:
        ts = time.strftime("%H:%M:%S", time.localtime(record.created))
        level = self._LEVEL_ABBREV.get(record.levelno, record.levelname[:5])
        # Shorten the logger name: "synthadoc.agents.ingest_agent" → "agents.ingest_agent"
        name = record.name.removeprefix("synthadoc.")
        msg = record.getMessage()
        base = f"{ts} {level}  {name} — {msg}"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


class _JsonlFormatter(logging.Formatter):
    """Newline-delimited JSON — one record per line.

    Every record includes the standard fields plus any extras set by a
    LoggerAdapter (job_id, operation, wiki, trace_id).
    """

    def format(self, record: logging.LogRecord) -> str:
        obj: dict = {
            "ts":      self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level":   record.levelname,
            "logger":  record.name,
            "msg":     record.getMessage(),
        }
        # Structured extras injected via LoggerAdapter.extra
        for key in ("job_id", "operation", "wiki", "trace_id"):
            if hasattr(record, key):
                obj[key] = getattr(record, key)
        if record.exc_info:
            obj["exc"] = self.formatException(record.exc_info)
        return json.dumps(obj, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def setup_logging(
    wiki_root: Path,
    cfg: Optional["LogsConfig"] = None,
    verbose: bool = False,
) -> None:
    """Configure root logger with console + rotating file handlers.

    Parameters
    ----------
    wiki_root:
        Wiki root directory. Log file is written to
        ``<wiki_root>/.synthadoc/logs/synthadoc.log``.
    cfg:
        ``LogsConfig`` from the loaded project config. When *None*, defaults
        from ``LogsConfig`` are used (level=INFO, max_file_mb=5, backup_count=5).
    verbose:
        If *True*, overrides ``cfg.level`` to DEBUG on the console handler.
        Equivalent to passing ``level = "DEBUG"`` in config but scoped to the
        current server invocation (e.g. ``synthadoc serve --verbose``).

    Safe to call multiple times — subsequent calls are no-ops (handlers are
    only added if the root logger has none yet).
    """
    root = logging.getLogger()
    if root.handlers:
        return  # already configured (e.g. in tests or when called twice)

    # Resolve settings — fall back to dataclass defaults when cfg is absent
    if cfg is None:
        from synthadoc.config import LogsConfig as _LC
        cfg = _LC()

    _LEVELS = {"DEBUG": logging.DEBUG, "INFO": logging.INFO,
               "WARNING": logging.WARNING, "ERROR": logging.ERROR}
    console_level = logging.DEBUG if verbose else _LEVELS.get(cfg.level.upper(), logging.INFO)

    root.setLevel(logging.DEBUG)

    # --- Console handler ---
    console = logging.StreamHandler()
    console.setLevel(console_level)
    console.setFormatter(_ConsoleFormatter())
    root.addHandler(console)

    # --- Rotating file handler ---
    logs_dir = wiki_root / ".synthadoc" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "synthadoc.log"

    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=cfg.max_file_mb * 1024 * 1024,
        backupCount=cfg.backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(_JsonlFormatter())
    root.addHandler(file_handler)

    # --- Suppress noisy third-party loggers ---
    for noisy in ("httpx", "httpcore", "uvicorn.access", "anthropic", "openai",
                  "aiosqlite", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger(__name__).info(
        "Logging initialised — wiki: %s  level: %s  file: %s  "
        "rotation: %d MB × %d files",
        wiki_root.name,
        logging.getLevelName(console_level),
        log_path,
        cfg.max_file_mb,
        cfg.backup_count,
    )


def get_job_logger(logger_name: str, job_id: str, operation: str, wiki: str) -> logging.LoggerAdapter:
    """Return a LoggerAdapter that injects job context into every log record.

    Usage::

        log = get_job_logger(__name__, job_id="abc123", operation="ingest", wiki="history-of-computing")
        log.info("Page created: %s", slug)
        # → {"ts": "...", "level": "INFO", ..., "job_id": "abc123", "operation": "ingest", "wiki": "history-of-computing", "msg": "Page created: alan-turing"}
    """
    return logging.LoggerAdapter(
        logging.getLogger(logger_name),
        extra={"job_id": job_id, "operation": operation, "wiki": wiki},
    )
