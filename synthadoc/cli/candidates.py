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

from synthadoc.cli.main import app

staging_app = typer.Typer(name="staging", help="Manage staging policy for new wiki pages.")
candidates_app = typer.Typer(name="candidates", help="Review, promote, or discard candidate pages.")
app.add_typer(staging_app)
app.add_typer(candidates_app)


def _cfg_path(root: Path) -> Path:
    return root / ".synthadoc" / "config.toml"


def _write_toml(raw: dict, path: Path) -> None:
    lines = []
    for section, value in raw.items():
        if isinstance(value, dict):
            lines.append(f"[{section}]")
            for k, v in value.items():
                lines.append(f"{k} = {json.dumps(v)}")
            lines.append("")
        else:
            lines.insert(0, f"{section} = {json.dumps(value)}")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


@staging_app.command("policy")
def staging_policy_cmd(
    policy: Optional[str] = typer.Argument(None, help="off | all | threshold"),
    min_confidence: Optional[str] = typer.Option(None, "--min-confidence"),
    wiki_root: Optional[str] = typer.Option(None, "--wiki-root"),
) -> None:
    """Show or set the staging policy."""
    root = Path(wiki_root) if wiki_root else Path(".")
    cfg_file = _cfg_path(root)
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

    raw.setdefault("ingest", {})["staging_policy"] = policy
    if min_confidence:
        raw["ingest"]["staging_confidence_min"] = min_confidence

    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    _write_toml(raw, cfg_file)
    msg = f"Staging policy updated: {policy}"
    if policy == "threshold" and min_confidence:
        msg += f" (min-confidence: {min_confidence})"
    typer.echo(msg)
    typer.echo("Takes effect on next ingest job — no restart needed.")


@candidates_app.command("list")
def candidates_list(
    wiki_root: Optional[str] = typer.Option(None, "--wiki-root"),
) -> None:
    """List all candidate pages awaiting review."""
    root = Path(wiki_root) if wiki_root else Path(".")
    cand_dir = root / "wiki" / "candidates"
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
    wiki_root: Optional[str] = typer.Option(None, "--wiki-root"),
) -> None:
    """Promote candidate(s) to the main wiki."""
    root = Path(wiki_root) if wiki_root else Path(".")
    cand_dir = root / "wiki" / "candidates"
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
    wiki_root: Optional[str] = typer.Option(None, "--wiki-root"),
) -> None:
    """Discard candidate page(s)."""
    root = Path(wiki_root) if wiki_root else Path(".")
    cand_dir = root / "wiki" / "candidates"

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
