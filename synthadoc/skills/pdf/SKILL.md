---
name: pdf
version: "1.0"
description: Extract text from PDF documents
entry:
  script: scripts/main.py
  class: PdfSkill
triggers:
  extensions:
    - ".pdf"
  intents:
    - "pdf"
    - "research paper"
    - "document"
requires:
  - pypdf
  - pdfminer.six
author: axoviq.com
license: AGPL-3.0-or-later
---

# PDF Skill

Extracts text from PDF files using `pypdf` as the primary parser, with
`pdfminer.six` as a fallback for CJK fonts that pypdf cannot decode
(detected when pypdf yields fewer than 50 characters per page on average).

## When this skill is used

- Source path ends with `.pdf`
- User intent contains: `pdf`, `research paper`, `document`

## Scripts

- `scripts/main.py` — `PdfSkill` class

## References

- `references/cjk-notes.md` — notes on CJK font handling
