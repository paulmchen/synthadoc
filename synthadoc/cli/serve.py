# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import os
import socket
from pathlib import Path
from typing import Optional

import typer

from synthadoc.cli.main import app
from synthadoc.cli.install import resolve_wiki_path

_PROVIDER_HOSTS = {
    "anthropic": ("api.anthropic.com", 443),
    "openai":    ("api.openai.com", 443),
}


def _check_port(port: int) -> None:
    """Fail early if the port is already bound by another process."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            raise SystemExit(
                f"\nError: port {port} is already in use.\n"
                f"Another synthadoc server (or a different process) is listening on that port.\n\n"
                f"  Option 1 — Stop the existing process and retry.\n"
                f"  Option 2 — Use a different port:\n"
                f"               synthadoc serve -w <wiki> --port {port + 1}\n"
                f"             (update the Server URL in the Obsidian plugin settings to match)\n"
            )


def _check_wiki(root: Path) -> None:
    """Fail early if the wiki directory is missing or incomplete."""
    if not root.exists():
        raise SystemExit(
            f"\nError: wiki directory not found: {root}\n"
            f"Run 'synthadoc install <name> --target <dir>' to create a wiki,\n"
            f"or check that the --wiki name matches a registered wiki.\n"
        )
    wiki_dir = root / "wiki"
    if not wiki_dir.is_dir():
        raise SystemExit(
            f"\nError: {root} does not look like a synthadoc wiki (missing wiki/ subfolder).\n"
            f"If this is a new wiki, run 'synthadoc install' to set it up properly.\n"
        )
    if not os.access(wiki_dir, os.W_OK):
        raise SystemExit(
            f"\nError: wiki directory is not writable: {wiki_dir}\n"
            f"Check file permissions.\n"
        )


def _check_network(provider: str) -> None:
    """Warn (don't block) if the provider API host is unreachable."""
    target = _PROVIDER_HOSTS.get(provider)
    if not target:
        return  # ollama or unknown — skip
    host, port = target
    try:
        with socket.create_connection((host, port), timeout=3):
            pass
    except OSError:
        typer.echo(
            f"Warning: cannot reach {host}:{port} — network may be unavailable or blocked.\n"
            f"The server will start, but ingest and query jobs will fail until connectivity\n"
            f"is restored. If you use a proxy, ensure it is configured in your environment.\n",
            err=True,
        )


@app.command("serve")
def serve_cmd(
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
    port: Optional[int] = typer.Option(None, "--port",
        help="Port override. Defaults to [server] port in config (7070)."),
    mcp_only: bool = typer.Option(False, "--mcp-only"),
    http_only: bool = typer.Option(False, "--http-only"),
    verbose: bool = typer.Option(False, "--verbose", "-v",
        help="Set console log level to DEBUG (file always logs DEBUG)."),
):
    """Start MCP + HTTP API servers (localhost only).

    Each wiki declares its port in .synthadoc/config.toml:

        [server]
        port = 7071

    Run one server per wiki on its own port, then set the matching
    Server URL in the Obsidian plugin settings for each vault.
    """
    import uvicorn
    from synthadoc.config import load_config
    from synthadoc.core.logging_config import setup_logging

    root = resolve_wiki_path(wiki) if wiki else Path(".")
    cfg = load_config(project_config=root / ".synthadoc" / "config.toml")
    effective_port = port if port is not None else cfg.server.port
    provider = cfg.agents.resolve("ingest").provider

    # Pre-flight checks — run before binding the port or starting workers
    _check_wiki(root)

    # Logging — must come after wiki root is validated so the logs dir can be created
    setup_logging(root, cfg=cfg.logs, verbose=verbose)

    from synthadoc.providers import _require_env
    if provider == "anthropic":
        _require_env("ANTHROPIC_API_KEY", "Anthropic", "https://console.anthropic.com/")
    elif provider == "openai":
        _require_env("OPENAI_API_KEY", "OpenAI", "https://platform.openai.com/api-keys")

    if not mcp_only:
        _check_port(effective_port)

    _check_network(provider)

    from synthadoc.cli.logo import print_banner
    mode = "MCP (stdio)" if mcp_only else "HTTP" if http_only else "HTTP + MCP"
    print_banner(port=effective_port, wiki=str(root), mode=mode)

    if not mcp_only:
        from synthadoc.integration.http_server import create_app
        http_app = create_app(wiki_root=root)
        uvicorn.run(http_app, host="127.0.0.1", port=effective_port,
                    log_level="warning")
    else:
        from synthadoc.integration.mcp_server import create_mcp_server
        mcp = create_mcp_server(wiki_root=root)
        mcp.run()
