# Synthadoc Hook Library

This folder contains ready-to-use hook scripts for common Synthadoc workflows.
Copy a script to your wiki root, then wire it up in `.synthadoc/config.toml`.

## How hooks work

Hooks are shell commands that fire on lifecycle events. They receive a JSON
context object on stdin and run either in the background (default) or blocking.

```toml
# .synthadoc/config.toml

[hooks]
on_ingest_complete = "python git-auto-commit.py"
on_lint_complete   = { cmd = "python notify-slack.py", blocking = false }
```

Two events are available in v0.1:

| Event | Fires when |
|-------|------------|
| `on_ingest_complete` | A source is successfully ingested |
| `on_lint_complete` | A lint run finishes |

See [docs/design.md — Section 12](../docs/design.md) for the full context
JSON schema for each event.

## Available hooks

| Script | Event | What it does |
|--------|-------|--------------|
| [`git-auto-commit.py`](git-auto-commit.py) | `on_ingest_complete` | Commits wiki changes to a local git repo after every ingest |

## Contributing a hook

1. Create a Python script in this folder
2. Add the standard header block (see existing scripts for the template)
3. Open a pull request — one script per PR, include a one-line entry in the
   table above

### Header template

```python
"""
Hook: <name>
Event: <on_ingest_complete | on_lint_complete>
Description: One sentence describing what this hook does.
Dependencies: list any non-stdlib requirements (e.g. requests, git)

Setup:
  1. ...
  2. ...
"""
```

### Guidelines

- Read all input from `sys.stdin` (JSON) — never from files or env vars
- Write human-readable status to `sys.stderr` (not stdout)
- Exit `0` on success, non-zero on failure
- Keep scripts self-contained — no shared utilities between hook scripts
- Test with a real wiki before submitting
