---
name: markdown
version: "1.0"
description: Ingest Markdown and plain text files
entry:
  script: scripts/main.py
  class: MarkdownSkill
triggers:
  extensions:
    - ".md"
    - ".txt"
  intents:
    - "markdown"
    - "text file"
    - "notes"
requires: []
author: axoviq.com
license: AGPL-3.0-or-later
---

# Markdown Skill

Reads a Markdown or plain text file and returns its content verbatim.

## When this skill is used

- Source path ends with `.md` or `.txt`
- User intent contains: `markdown`, `text file`, `notes`
