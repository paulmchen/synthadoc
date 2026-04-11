---
name: xlsx
version: "1.0"
description: Extract data from Excel and CSV files
entry:
  script: scripts/main.py
  class: XlsxSkill
triggers:
  extensions:
    - ".xlsx"
    - ".csv"
  intents:
    - "spreadsheet"
    - "excel"
    - "csv"
requires:
  - openpyxl
author: axoviq.com
license: AGPL-3.0-or-later
---

# XLSX Skill

Reads `.xlsx` files using `openpyxl` and `.csv` files using the stdlib `csv`
module, returning all rows as comma-separated text.

## When this skill is used

- Source path ends with `.xlsx` or `.csv`
- User intent contains: `spreadsheet`, `excel`, `csv`
