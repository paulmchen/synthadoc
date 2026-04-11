---
name: docx
version: "1.0"
description: Extract text from Microsoft Word documents
entry:
  script: scripts/main.py
  class: DocxSkill
triggers:
  extensions:
    - ".docx"
  intents:
    - "word document"
    - "docx"
requires:
  - python-docx
author: axoviq.com
license: AGPL-3.0-or-later
---

# DOCX Skill

Extracts paragraph text from `.docx` files using `python-docx`.

## When this skill is used

- Source path ends with `.docx`
- User intent contains: `word document`, `docx`
