---
title: Dashboard
tags: [dashboard]
status: active
confidence: high
created: '2026-04-08'
sources: []
---

# History of Computing — Dashboard

> Requires the **Dataview** community plugin (Settings → Community plugins → Browse → "Dataview").

---

## Contradicted pages — need review

```dataview
TABLE status, confidence, created
FROM "wiki"
WHERE status = "contradicted"
SORT created DESC
```

*These pages were flagged during ingest as conflicting with a newer source.
Open each one, resolve the conflict, then change `status` to `active`.*

---

## Orphan pages — no inbound links

```dataview
TABLE status, created
FROM "wiki"
WHERE length(file.inlinks) = 0
AND file.name != "index"
AND file.name != "dashboard"
AND file.name != "purpose"
SORT created DESC
```

*These pages exist but nothing links to them.
Add `[[page-name]]` to a related page or to [[index]].*

---

## Recently added

```dataview
TABLE status, confidence
FROM "wiki"
WHERE file.name != "index" AND file.name != "dashboard" AND file.name != "purpose"
SORT created DESC
LIMIT 10
```
