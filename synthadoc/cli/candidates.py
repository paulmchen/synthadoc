# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
from __future__ import annotations

import json
import shutil
import tomllib
from pathlib import Path
from typing import Optional

import typer
import yaml

from synthadoc.cli._wiki import resolve_wiki
from synthadoc.cli.install import resolve_wiki_path
from synthadoc.cli.main import app

staging_app = typer.Typer(name="staging", help="Manage staging policy for new wiki pages.")
candidates_app = typer.Typer(name="candidates", help="Review, promote, or discard candidate pages.")
app.add_typer(staging_app)
app.add_typer(candidates_app)


def _cfg_path(root: Path) -> Path:
    return root / ".synthadoc" / "config.toml"


def _paths(wiki: Optional[str]) -> tuple[Path, Path, Path]:
    """Return (root, cfg_file, cand_dir) from the --wiki option."""
    root = resolve_wiki_path(resolve_wiki(wiki))
    return root, _cfg_path(root), root / "wiki" / "candidates"


def _toml_value(v: object) -> str:
    """Serialise a Python value as a TOML literal (not JSON)."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        return json.dumps(v)  # double-quoted string — same as JSON
    if isinstance(v, dict):
        pairs = ", ".join(f"{k} = {_toml_value(val)}" for k, val in v.items())
        return "{" + pairs + "}"
    if isinstance(v, list):
        items = ", ".join(_toml_value(i) for i in v)
        return "[" + items + "]"
    return json.dumps(v)


def _patch_toml(path: Path, section: str, updates: dict) -> None:
    """Patch specific keys in a TOML section without touching other lines or comments."""
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = text.splitlines()

    section_header = f"[{section}]"
    in_target = False
    patched_keys: set[str] = set()
    result: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_target:
                # End of target section — append any keys not yet seen
                for k, v in updates.items():
                    if k not in patched_keys:
                        result.append(f"{k} = {_toml_value(v)}")
                        patched_keys.add(k)
            in_target = stripped == section_header
            result.append(line)
            continue

        if in_target and "=" in stripped and not stripped.startswith("#"):
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                result.append(f"{key} = {_toml_value(updates[key])}")
                patched_keys.add(key)
                continue

        result.append(line)

    # Handle keys not found if target section was last (or never closed)
    if in_target:
        for k, v in updates.items():
            if k not in patched_keys:
                result.append(f"{k} = {_toml_value(v)}")
                patched_keys.add(k)

    # If section didn't exist at all, append it
    if not patched_keys:
        if result and result[-1].strip():
            result.append("")
        result.append(f"[{section}]")
        for k, v in updates.items():
            result.append(f"{k} = {_toml_value(v)}")

    path.write_text("\n".join(result) + "\n", encoding="utf-8")


@staging_app.command("policy")
def staging_policy_cmd(
    policy: Optional[str] = typer.Argument(None, help="off | all | threshold"),
    min_confidence: Optional[str] = typer.Option(None, "--min-confidence"),
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w", help="Wiki name or path"),
) -> None:
    """Show or set the staging policy."""
    root, cfg_file, _ = _paths(wiki)
    raw = tomllib.loads(cfg_file.read_text()) if cfg_file.exists() else {}

    if policy is None:
        current = raw.get("ingest", {}).get("staging_policy", "off")
        min_c = raw.get("ingest", {}).get("staging_confidence_min", "high")
        typer.echo(f"Staging policy: {current}")
        if current == "threshold":
            typer.echo(f"Minimum confidence for auto-promote: {min_c}")
        return

    if policy not in ("off", "all", "threshold"):
        typer.echo("Policy must be one of: off, all, threshold")
        raise typer.Exit(1)

    updates = {"staging_policy": policy}
    if min_confidence:
        updates["staging_confidence_min"] = min_confidence

    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    _patch_toml(cfg_file, "ingest", updates)
    msg = f"Staging policy updated: {policy}"
    if policy == "threshold" and min_confidence:
        msg += f" (min-confidence: {min_confidence})"
    typer.echo(msg)
    typer.echo("Takes effect on next ingest job — no restart needed.")


@candidates_app.command("list")
def candidates_list(
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w", help="Wiki name or path"),
) -> None:
    """List all candidate pages awaiting review."""
    _, _, cand_dir = _paths(wiki)
    pages = sorted(cand_dir.glob("*.md")) if cand_dir.exists() else []
    if not pages:
        typer.echo("No candidates.")
        return
    typer.echo(f"Candidates ({len(pages)}):")
    for p in pages:
        fm = _read_frontmatter(p)
        conf = fm.get("confidence", "?")
        created = fm.get("created", "?")
        typer.echo(f"  {p.stem:<30} confidence: {conf:<8} ingested: {created}")


@candidates_app.command("promote")
def candidates_promote(
    slug: Optional[str] = typer.Argument(None),
    all_: bool = typer.Option(False, "--all"),
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w", help="Wiki name or path"),
) -> None:
    """Promote candidate(s) to the main wiki."""
    root, _, cand_dir = _paths(wiki)
    wiki_dir = root / "wiki"

    targets = list(cand_dir.glob("*.md")) if all_ else []
    if not all_ and slug:
        targets = [cand_dir / f"{slug}.md"]

    for src in targets:
        if not src.exists():
            typer.echo(f"  Not found: {src.stem}")
            continue
        dest = wiki_dir / src.name
        if dest.exists():
            typer.echo(f"  Skipped {src.stem} — already exists in wiki/")
            continue
        shutil.move(str(src), str(dest))
        typer.echo(f"  Promoted {src.stem} → wiki/{src.name}")


@candidates_app.command("discard")
def candidates_discard(
    slug: Optional[str] = typer.Argument(None),
    all_: bool = typer.Option(False, "--all"),
    wiki: Optional[str] = typer.Option(None, "--wiki", "-w", help="Wiki name or path"),
) -> None:
    """Discard candidate page(s)."""
    _, _, cand_dir = _paths(wiki)

    targets = list(cand_dir.glob("*.md")) if all_ else []
    if not all_ and slug:
        targets = [cand_dir / f"{slug}.md"]

    for src in targets:
        src.unlink(missing_ok=True)
        typer.echo(f"  Discarded {src.stem}")


def _read_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        return yaml.safe_load(parts[1]) or {}
    except Exception:
        return {}
