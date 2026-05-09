---
title: Dashboard
tags: [dashboard]
status: active
confidence: high
created: 2026-05-09
sources: []
orphan: false
aliases: []
---

# AI Research Tracker — Dashboard

## Contradicted Pages

```dataview
TABLE dateformat(created, "MMM dd, yyyy") AS "Created", status, confidence
FROM "wiki"
WHERE status = "contradicted"
SORT created DESC
```

## Orphan Pages

```dataview
TABLE dateformat(created, "MMM dd, yyyy") AS "Created", status
FROM "wiki"
WHERE orphan = true
SORT created DESC
```

## Recently Added

```dataview
TABLE dateformat(created, "MMM dd, yyyy") AS "Added", status, confidence
FROM "wiki"
WHERE file.name != "index" AND file.name != "dashboard" AND file.name != "purpose"
SORT created DESC
LIMIT 10
```
