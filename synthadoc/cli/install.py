# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path
from typing import Optional

import typer

from synthadoc.cli.main import app
from synthadoc.cli._port import find_free_port as _find_free_port, _DEFAULT_PORT
from synthadoc import errors as E

_REGISTRY = Path.home() / ".synthadoc" / "wikis.json"

_DEMOS = {
    "history-of-computing": Path(__file__).parent.parent / "demos" / "history-of-computing",
}


def _read_registry() -> dict:
    if _REGISTRY.exists():
        return json.loads(_REGISTRY.read_text(encoding="utf-8"))
    return {}


def _write_registry(data: dict) -> None:
    _REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    _REGISTRY.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _run_scaffold(dest: Path, domain: str):
    """Try to run ScaffoldAgent. Returns ScaffoldResult or None if no API key is set."""
    import asyncio
    import os
    from synthadoc.config import load_config
    from synthadoc.providers import make_provider

    cfg = load_config(project_config=dest / ".synthadoc" / "config.toml")
    provider_name = cfg.agents.resolve("ingest").provider

    _KEY_ENV = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "groq": "GROQ_API_KEY",
    }
    env_var = _KEY_ENV.get(provider_name)
    if env_var and not os.environ.get(env_var, "").strip():
        return None  # no key — caller will fall back to static template

    try:
        provider = make_provider("ingest", cfg)
        from synthadoc.agents.scaffold_agent import ScaffoldAgent
        agent = ScaffoldAgent(provider=provider)
        return asyncio.run(agent.scaffold(domain=domain))
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Scaffold LLM call failed: %s", exc)
        typer.echo(f"  Warning: LLM scaffold failed ({exc})", err=True)
        return None


def resolve_wiki_path(wiki: str) -> Path:
    """Resolve a --wiki value to an absolute Path.

    Lookup order:
    1. Registry name match  — ``synthadoc status -w history-of-computing``
    2. Filesystem path      — ``synthadoc status -w ~/wikis/history-of-computing``

    If neither resolves to an existing directory, returns the path as-is and
    lets the caller surface the error (e.g. Orchestrator will fail clearly).
    """
    registry = _read_registry()
    if wiki in registry:
        return Path(registry[wiki]["path"])
    return Path(wiki)


@app.command("install")
def install_cmd(
    name: str = typer.Argument(help="Name for the new wiki"),
    target: str = typer.Option(..., "--target", "-t", help="Parent directory to install into"),
    demo: bool = typer.Option(False, "--demo", "-d", help="Install from a demo template matching <name>"),
    domain: str = typer.Option("General", "--domain", help="Knowledge domain (fresh wikis only)"),
    port: Optional[int] = typer.Option(None, "--port", help="Server port (default: auto-detect from 7070)"),
):
    """Create a new wiki, optionally from a demo template.

    Examples:

      synthadoc install my-research --target ~/wikis

      synthadoc install history-of-computing --target ~/wikis --demo
    """
    dest = (Path(target) / name).resolve()

    # Registry check first — same name cannot be installed twice regardless of --target path
    registry = _read_registry()
    if name in registry:
        entry = registry[name]
        kind = f"demo ({entry['demo']})" if entry.get("demo") else "wiki"
        E.cli_error(
            E.WIKI_ALREADY_EXISTS,
            f"'{name}' is already installed as a {kind} at {entry['path']}.",
            f"To reinstall: synthadoc uninstall {name}  then install again.",
        )

    if dest.exists():
        E.cli_error(
            E.WIKI_ALREADY_EXISTS,
            f"'{name}' already exists at {dest} but is not tracked by synthadoc.",
            f"It may be a leftover from a previous install. To remove it:\n"
            f"  rm -rf \"{dest}\"    # Linux / macOS\n"
            f"  Remove-Item -Recurse -Force \"{dest}\"    # Windows PowerShell\n"
            f"Then run install again.",
        )

    # ── Port resolution ────────────────────────────────────────────────────────
    if port is not None:
        effective_port = port
    else:
        effective_port = _find_free_port(_DEFAULT_PORT)
        if effective_port != _DEFAULT_PORT:
            confirmed = typer.confirm(
                f"Port {_DEFAULT_PORT} is already in use. "
                f"Install '{name}' on port {effective_port} instead?"
            )
            if not confirmed:
                typer.echo("Tip: use --port <N> to specify a port manually.", err=True)
                raise typer.Exit(1)

    if demo:
        if name not in _DEMOS:
            E.cli_error(
                E.WIKI_DEMO_NOT_FOUND,
                f"No demo template named '{name}'.",
                f"Available demos: {', '.join(_DEMOS)}",
            )
        shutil.copytree(_DEMOS[name], dest)
        # Ensure operational directories exist — the demo template may not include
        # empty dirs (git doesn't track them) and shutil.copytree won't create them.
        (dest / ".synthadoc" / "logs").mkdir(parents=True, exist_ok=True)
    else:
        from synthadoc.cli._init import init_wiki
        init_wiki(dest, domain, port=effective_port)

        # ── LLM scaffold ──────────────────────────────────────────────────────
        typer.echo("Generating domain-specific scaffold...")
        scaffold_result = _run_scaffold(dest, domain)
        if scaffold_result:
            (dest / "wiki" / "index.md").write_text(
                scaffold_result.index_md, encoding="utf-8", newline="\n")
            (dest / "AGENTS.md").write_text(
                scaffold_result.agents_md, encoding="utf-8", newline="\n")
            (dest / "wiki" / "purpose.md").write_text(
                scaffold_result.purpose_md, encoding="utf-8", newline="\n")
            dashboard_path = dest / "wiki" / "dashboard.md"
            dash = dashboard_path.read_text(encoding="utf-8")
            dash = dash.replace(
                f"# {domain} — Dashboard",
                f"# {domain} — Dashboard\n\n{scaffold_result.dashboard_intro}",
                1,
            )
            dashboard_path.write_text(dash, encoding="utf-8", newline="\n")
            typer.echo("  Scaffold complete — domain-specific content generated.")
        else:
            typer.echo(
                "  Scaffold skipped — static templates written.\n"
                f"  Run 'synthadoc scaffold -w {name}' after setting your LLM API key"
                " to generate domain-specific content."
            )

    registry = _read_registry()
    registry[name] = {
        "path": str(dest),
        "demo": name if demo else None,
        "installed": date.today().isoformat(),
    }
    _write_registry(registry)

    typer.echo(f"Wiki '{name}' installed.")
    typer.echo(f"  Port   {effective_port}")
    typer.echo(f"Start:   synthadoc serve -w {name}")


@app.command("list")
def list_cmd():
    """List all installed wikis."""
    registry = _read_registry()
    if not registry:
        typer.echo("No wikis installed. Run 'synthadoc install' to create one.")
        return
    for name, entry in registry.items():
        demo_tag = f"  [demo]" if entry.get("demo") else ""
        installed = entry.get("installed", "")
        typer.echo(f"{name:<30}  installed: {installed}{demo_tag}")


@app.command("uninstall")
def uninstall_cmd(
    name: str = typer.Argument(help="Name of the wiki to remove"),
):
    """Permanently delete an installed wiki.

    Requires two confirmations: a y/N prompt followed by typing the wiki name.
    There is no --yes flag — this operation is irreversible.
    """
    registry = _read_registry()

    if name not in registry:
        E.cli_error(
            E.WIKI_NOT_REGISTERED,
            f"Wiki '{name}' is not in the registry.",
            f"It may have already been uninstalled or was never installed via `synthadoc install`.\n"
            f"If the directory still exists, remove it manually:\n"
            f"  rm -rf <path-to-wiki>    # Linux / macOS\n"
            f"  Remove-Item -Recurse -Force <path-to-wiki>    # Windows PowerShell",
        )

    dest = Path(registry[name]["path"])

    if not dest.exists():
        typer.echo(f"Wiki '{name}' no longer exists on disk — removing from registry.")
        del registry[name]
        _write_registry(registry)
        raise typer.Exit(0)

    # First confirmation
    typer.confirm(
        f"Delete wiki '{name}' at {dest} and all its contents?",
        abort=True,
    )

    # Second confirmation — must type the exact name
    typed = typer.prompt(f"Type '{name}' to confirm permanent deletion")
    if typed != name:
        typer.echo("Name did not match — aborted. Nothing was deleted.")
        raise typer.Exit(1)

    shutil.rmtree(dest)
    del registry[name]
    _write_registry(registry)
    typer.echo(f"Wiki '{name}' removed.")
