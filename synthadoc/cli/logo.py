# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
"""Terminal banner and web index for Synthadoc."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# ──────────────────────────────────────────────
#  ASCII art — open book inside a circular badge
# ──────────────────────────────────────────────
_LOGO = r"""
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
"""

# Name banner (plain ASCII, no font rendering issues)
_NAME = r"""
  +--------------------------------------------+
  |   S Y N T H A D O C                       |
  |   Domain-agnostic LLM wiki engine          |
  +--------------------------------------------+
"""

# ──────────────────────────────────────────────
#  ANSI helpers
# ──────────────────────────────────────────────
_GREEN  = "\033[32m"
_CYAN   = "\033[36m"
_YELLOW = "\033[33m"
_WHITE  = "\033[97m"
_DIM    = "\033[2m"
_BOLD   = "\033[1m"
_RESET  = "\033[0m"


def _color_supported() -> bool:
    if os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _c(code: str, text: str, use_color: bool) -> str:
    return f"{code}{text}{_RESET}" if use_color else text


# ──────────────────────────────────────────────
#  Public API
# ──────────────────────────────────────────────
def print_banner(
    port: int,
    wiki: str,
    version: str = "0.1.0",
    mode: str = "HTTP + MCP",
) -> None:
    """Print the startup banner to stdout."""
    use_color = _color_supported()

    logo_lines = _LOGO.strip("\n").splitlines()
    info_lines = [
        _c(_BOLD + _WHITE,  f"  S Y N T H A D O C  {version}", use_color),
        _c(_DIM,            f"  {'-' * 32}", use_color),
        _c(_CYAN,           "  Domain-agnostic LLM wiki engine", use_color),
        "",
        _c(_WHITE,          f"  Mode:  {mode}", use_color),
        _c(_WHITE,          f"  Port:  {port}", use_color),
        _c(_WHITE,          f"  Wiki:  {wiki}", use_color),
        _c(_WHITE,          f"  PID:   {os.getpid()}", use_color),
        "",
        _c(_DIM,            "  https://github.com/paulmchen/synthadoc", use_color),
    ]

    # Pad shorter list so we can zip
    n = max(len(logo_lines), len(info_lines))
    logo_lines += [""] * (n - len(logo_lines))
    info_lines += [""] * (n - len(info_lines))

    logo_width = max(len(l) for l in logo_lines)

    print()
    for logo_line, info_line in zip(logo_lines, info_lines):
        colored_logo = _c(_GREEN, f"{logo_line:<{logo_width}}", use_color)
        print(f"  {colored_logo}    {info_line}")
    print()


def banner_text(version: str = "0.1.0") -> str:
    """Return the plain-text banner (no ANSI) for README / web index."""
    logo_lines = _LOGO.strip("\n").splitlines()
    name_lines = _NAME.strip("\n").splitlines()

    lines: list[str] = []
    lines.append("")
    lines.extend(logo_lines)
    lines.append("")
    lines.extend(name_lines)
    lines.append(f"  Version {version}  —  Domain-agnostic LLM wiki engine")
    lines.append("  https://github.com/paulmchen/synthadoc")
    lines.append("")
    return "\n".join(lines)
