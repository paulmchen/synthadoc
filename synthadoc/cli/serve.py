# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import os
import socket
import sys
import time
import subprocess
from pathlib import Path
from typing import Optional

import typer

from synthadoc.cli.main import app
from synthadoc.cli.install import resolve_wiki_path
from synthadoc import errors as E

# Internal env var set on the detached child to suppress duplicate banner output.
_NO_BANNER_ENV = "_SYNTHADOC_NO_BANNER"

_PROVIDER_HOSTS = {
    "anthropic": ("api.anthropic.com", 443),
    "openai":    ("api.openai.com", 443),
    "gemini":    ("generativelanguage.googleapis.com", 443),
    "groq":      ("api.groq.com", 443),
}

# Loopback addresses — the Obsidian plugin always connects via 127.0.0.1 for these.
_LOOPBACK_ADDRS: frozenset[str] = frozenset({"127.0.0.1", "::1", "localhost"})
# "All interfaces" binds — plugin still reaches the server via 127.0.0.1 locally.
_ANY_IFACE_ADDRS: frozenset[str] = frozenset({"0.0.0.0", "::"})


def _plugin_url(host: str, port: int) -> str:
    """Return the URL the Obsidian plugin should use to reach the server.

    When the server binds to a loopback or any-interface address, the plugin
    always runs on the same machine, so 127.0.0.1 works.  When bound to a
    specific external address, use that address directly so remote vaults
    can connect.
    """
    if host in _LOOPBACK_ADDRS or host in _ANY_IFACE_ADDRS:
        return f"http://127.0.0.1:{port}"
    return f"http://{host}:{port}"


def _sync_plugin_config(wiki_root: Path, host: str, port: int) -> None:
    """Update the Obsidian plugin data.json if its serverUrl differs from the served address.

    Called at startup so that manual config.toml edits are automatically
    reflected in the plugin — the user only needs to reload Obsidian.
    Silently no-ops if the plugin is not installed in this vault.
    """
    import json
    data_json = wiki_root / ".obsidian" / "plugins" / "synthadoc" / "data.json"
    if not data_json.exists():
        return
    try:
        data = json.loads(data_json.read_text(encoding="utf-8"))
        expected_url = _plugin_url(host, port)
        if data.get("serverUrl") != expected_url:
            old_url = data.get("serverUrl", "(none)")
            data["serverUrl"] = expected_url
            data_json.write_text(json.dumps(data, indent=2), encoding="utf-8")
            typer.echo(
                f"Notice: plugin server URL updated {old_url!r} → {expected_url!r}.\n"
                f"Reload Obsidian (Cmd+R / Ctrl+R) if it is already open."
            )
    except Exception:
        pass  # never block startup due to a plugin config issue


def _sync_registry_port(wiki_name: str, port: int) -> None:
    """Update the registry port for a wiki when it differs (e.g. config.toml edited manually)."""
    from synthadoc.cli.install import _read_registry, _write_registry
    try:
        registry = _read_registry()
        if wiki_name in registry and registry[wiki_name].get("port") != port:
            registry[wiki_name]["port"] = port
            _write_registry(registry)
    except Exception:
        pass


def _check_port(port: int, host: str = "127.0.0.1") -> None:
    """Fail early if the port is already bound by another process on the target host."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if sys.platform == "win32":
            # SO_REUSEADDR on Windows lets any socket bind to an occupied port —
            # the opposite of what we want here.  SO_EXCLUSIVEADDRUSE correctly
            # fails the bind if anything else already holds the port.
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            # On POSIX, SO_REUSEADDR lets the check succeed on a TIME_WAIT port
            # (so a quick restart doesn't false-alarm) while still failing when
            # the port is actively held in LISTEN state by another process.
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
        except OSError:
            E.cli_error(
                E.SRV_PORT_IN_USE,
                f"Port {port} is already in use.",
                f"  Option 1 — Stop the existing process and retry.\n"
                f"  Option 2 — Use a different port:\n"
                f"               synthadoc serve -w <wiki> --port {port + 1}\n"
                f"             (update the Server URL in the Obsidian plugin settings to match)",
            )


def _check_wiki(root: Path, wiki_arg: str = "") -> None:
    """Fail early if the wiki directory is missing or incomplete."""
    if not root.exists():
        name = wiki_arg or root.name
        E.cli_error(
            E.WIKI_NOT_FOUND,
            f"Wiki directory not found: {root}",
            f"Run 'synthadoc install {name} --target <dir>' to create it,\n"
            f"or check that the --wiki name matches a registered wiki.",
        )
    wiki_dir = root / "wiki"
    if not wiki_dir.is_dir():
        E.cli_error(
            E.WIKI_INVALID,
            f"{root} does not look like a synthadoc wiki (missing wiki/ subfolder).",
            "If this is a new wiki, run 'synthadoc install' to set it up properly.",
        )
    if not os.access(wiki_dir, os.W_OK):
        E.cli_error(
            E.WIKI_NOT_WRITABLE,
            f"Wiki directory is not writable: {wiki_dir}",
            "Check file permissions.",
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


def _spawn_background(wiki_root: Path, effective_port: int, log_path: Path) -> None:
    """Detach the server as a background process and return to the shell."""
    # Strip --background / -b from the forwarded args.
    server_args = [a for a in sys.argv[1:] if a not in ("--background", "-b")]

    if sys.platform == "win32":
        # pythonw.exe runs Python with no console window at all — the child
        # process has zero console association, so the parent's CMD/PowerShell
        # window returns to the prompt as soon as the parent exits.
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        interpreter = str(pythonw) if pythonw.exists() else sys.executable
        cmd = [interpreter, "-m", "synthadoc"] + server_args
        popen_kwargs: dict = dict(
            args=cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            env={**os.environ, _NO_BANNER_ENV: "1"},
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    else:
        cmd = [sys.argv[0]] + server_args
        popen_kwargs = dict(
            args=cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            env={**os.environ, _NO_BANNER_ENV: "1"},
            start_new_session=True,
        )

    proc = subprocess.Popen(**popen_kwargs)

    # Persist PID so the user (or a stop command) can terminate the server.
    pid_path = wiki_root / ".synthadoc" / "server.pid"
    pid_path.write_text(str(proc.pid), encoding="utf-8")

    # Brief pause — detect immediate crashes before telling the user it worked.
    time.sleep(1.5)
    if proc.poll() is not None:
        E.cli_error(
            E.SRV_BG_CRASH,
            f"Background server exited immediately (code {proc.returncode}).",
            f"Check logs: {log_path}",
        )

    typer.echo(
        f"\nServer running in background\n"
        f"  PID   {proc.pid}\n"
        f"  Port  {effective_port}\n"
        f"  Logs  {log_path}\n"
        f"\nTo stop: kill {proc.pid}"
        + (f"  (or: taskkill /PID {proc.pid} /F)" if sys.platform == "win32" else "")
    )


def _apply_provider_override(cfg, provider_name: str) -> None:
    """Override the provider field on all agent configs in cfg in-place."""
    from synthadoc.config import KNOWN_PROVIDERS
    if provider_name not in KNOWN_PROVIDERS:
        E.cli_error(
            E.CFG_UNKNOWN_PROVIDER,
            f"Unknown provider: {provider_name!r}",
            f"Supported providers: {', '.join(sorted(KNOWN_PROVIDERS))}",
        )
    cfg.agents.default.provider = provider_name
    for slot in ("ingest", "query", "lint", "skill"):
        override = getattr(cfg.agents, slot, None)
        if override is not None:
            override.provider = provider_name


@app.command("serve")
def serve_cmd(
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w"),
    port: Optional[int] = typer.Option(None, "--port",
        help="Port override. Defaults to [server] port in config (7070)."),
    mcp_only: bool = typer.Option(False, "--mcp-only"),
    http_only: bool = typer.Option(False, "--http-only"),
    verbose: bool = typer.Option(False, "--verbose", "-v",
        help="Set console log level to DEBUG (file always logs DEBUG)."),
    background: bool = typer.Option(False, "--background", "-b",
        help="Detach the server to the background. Banner is shown then the shell is released; "
             "all subsequent logs go to the wiki log file."),
    provider_override: Optional[str] = typer.Option(
        None, "--provider",
        help="Override config.toml provider for all agents for this server session "
             "(e.g. anthropic, claude-code, opencode). Does not require editing config.toml.",
    ),
):
    """Start MCP + HTTP API servers (localhost only).

    Each wiki declares its port in .synthadoc/config.toml:

        [server]
        port = 7071

    Run one server per wiki on its own port, then set the matching
    Server URL in the Obsidian plugin settings for each vault.
    """
    from synthadoc.cli._wiki import resolve_wiki
    wiki = resolve_wiki(wiki)

    import uvicorn
    from synthadoc.config import load_config
    from synthadoc.core.logging_config import setup_logging

    root = resolve_wiki_path(wiki)
    cfg = load_config(project_config=root / ".synthadoc" / "config.toml")
    effective_port = port if port is not None else cfg.server.port

    if provider_override:
        _apply_provider_override(cfg, provider_override)

    provider = cfg.agents.resolve("ingest").provider

    # Warn when binding to an external interface — synthadoc has no built-in auth.
    if cfg.server.host not in _LOOPBACK_ADDRS:
        typer.echo(
            f"Warning: binding to {cfg.server.host!r} — server reachable from the network.\n"
            "synthadoc has no built-in authentication. Restrict access via firewall\n"
            "or network controls before exposing to untrusted networks.",
            err=True,
        )

    # Keep registry and plugin in sync if config.toml port was manually changed
    _sync_registry_port(wiki or "", effective_port)
    _sync_plugin_config(root, cfg.server.host, effective_port)

    # Pre-flight checks — run before binding the port or starting workers
    _check_wiki(root, wiki_arg=wiki or "")

    # Logging — must come after wiki root is validated so the logs dir can be created
    setup_logging(root, cfg=cfg.logs, verbose=verbose)

    from synthadoc.providers import _require_env
    if provider in ("claude-code", "opencode", "ollama"):
        pass  # CLI and local providers — no API key required
    elif provider == "anthropic":
        _require_env("ANTHROPIC_API_KEY", "Anthropic", "https://console.anthropic.com/")
    elif provider == "openai":
        _require_env("OPENAI_API_KEY", "OpenAI", "https://platform.openai.com/api-keys")
    elif provider == "gemini":
        _require_env("GEMINI_API_KEY", "Google Gemini",
                     "https://aistudio.google.com/app/apikey")
    elif provider == "groq":
        _require_env("GROQ_API_KEY", "Groq", "https://console.groq.com/keys")

    # Propagate web_search config to env so WebSearchSkill can read it
    os.environ.setdefault(
        "SYNTHADOC_WEB_SEARCH_MAX_RESULTS",
        str(cfg.web_search.max_results),
    )
    if cfg.web_search.provider == "tavily" and not os.environ.get("TAVILY_API_KEY"):
        typer.echo(
            "Warning: TAVILY_API_KEY is not set. Web search jobs will fail.\n"
            "Get a free key at https://tavily.com",
            err=True,
        )

    if not mcp_only:
        _check_port(effective_port, host=cfg.server.host)

    _check_network(provider)

    if not os.environ.get(_NO_BANNER_ENV):
        from synthadoc.cli.logo import print_banner
        mode = "MCP (stdio)" if mcp_only else "HTTP" if http_only else "HTTP + MCP"
        _agent_cfg = cfg.agents.resolve("default")
        _override_count = sum(
            1 for slot in ("ingest", "query", "lint", "skill")
            if getattr(cfg.agents, slot, None) is not None
        )
        _llm_note = f"(+ {_override_count} override{'s' if _override_count != 1 else ''})" if _override_count else ""
        print_banner(port=effective_port, wiki=str(root), mode=mode,
                     provider=_agent_cfg.provider, model=_agent_cfg.model,
                     llm_note=_llm_note)

    if background:
        log_path = root / ".synthadoc" / "logs" / "synthadoc.log"
        _spawn_background(root, effective_port, log_path)
        return

    if not mcp_only:
        from synthadoc.integration.http_server import create_app
        http_app = create_app(wiki_root=root)
        uvicorn.run(http_app, host=cfg.server.host, port=effective_port,
                    log_level="warning", log_config=None)
    else:
        from synthadoc.integration.mcp_server import create_mcp_server
        mcp = create_mcp_server(wiki_root=root)
        mcp.run()
