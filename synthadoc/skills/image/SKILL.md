---
name: image
version: "1.0"
description: Extract text from images using a vision LLM
entry:
  script: scripts/main.py
  class: ImageSkill
triggers:
  extensions:
    - ".png"
    - ".jpg"
    - ".jpeg"
    - ".webp"
    - ".gif"
    - ".tiff"
  intents:
    - "image"
    - "screenshot"
    - "diagram"
    - "photo"
requires: []
author: axoviq.com
license: AGPL-3.0-or-later
---

# Image Skill

Base64-encodes the image and returns it in `metadata` for the IngestAgent to
process via a vision-capable LLM. The `text` field is left empty at extract
time and filled in by the agent.

## When this skill is used

- Source path ends with `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, or `.tiff`
- User intent contains: `image`, `screenshot`, `diagram`, `photo`
