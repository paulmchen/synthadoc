#!/usr/bin/env python3
"""
Hook: git-auto-commit
Event: on_ingest_complete
Description: Commits wiki changes to a local git repo after every successful ingest.
Dependencies: git (must be installed; wiki root must be a git repository)

Setup:
  1. Copy this script to your wiki root:
       cp hooks/git-auto-commit.py /path/to/your/wiki/

  2. Initialise git in the wiki root (one-time, skip if already a repo):
       cd /path/to/your/wiki
       git init
       git add .
       git commit -m "init: initial wiki snapshot"

  3. Add to .synthadoc/config.toml:
       [hooks]
       on_ingest_complete = "python git-auto-commit.py"

  4. Restart the server:
       synthadoc serve -w <wiki-name>

After each ingest you will find a new commit in `git log` with a message like:
  wiki: ingest report.pdf → created alan-turing, updated computing-history
"""
import json
import os
import subprocess
import sys


def main() -> None:
    ctx = json.load(sys.stdin)

    wiki_root   = ctx.get("wiki", ".")
    source      = ctx.get("source", "unknown")
    created     = ctx.get("pages_created", [])
    updated     = ctx.get("pages_updated", [])

    # Build a meaningful commit message from the ingest result
    parts = []
    if created:
        parts.append(f"created {', '.join(created)}")
    if updated:
        parts.append(f"updated {', '.join(updated)}")
    summary = "; ".join(parts) if parts else "no page changes"

    source_name = os.path.basename(source)
    msg = f"wiki: ingest {source_name} → {summary}"

    # Stage all changes under wiki/
    subprocess.run(
        ["git", "-C", wiki_root, "add", "wiki/"],
        check=True,
        capture_output=True,
    )

    # Commit — tolerate "nothing to commit" gracefully
    result = subprocess.run(
        ["git", "-C", wiki_root, "commit", "-m", msg],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        # Print the short commit hash so it appears in the server log
        first_line = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
        print(f"git-auto-commit: {first_line}", file=sys.stderr)
    elif "nothing to commit" in (result.stdout + result.stderr):
        print("git-auto-commit: nothing to commit — skipped", file=sys.stderr)
    else:
        print(f"git-auto-commit error: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
