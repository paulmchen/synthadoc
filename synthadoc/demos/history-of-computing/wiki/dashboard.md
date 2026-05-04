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
TABLE dateformat(created, "MMM dd, yyyy HH:mm:ss") AS "Created", status, confidence
FROM "wiki"
WHERE status = "contradicted"
SORT created DESC
```

*These pages were flagged during ingest as conflicting with a newer source.
Open each one, resolve the conflict, then change `status` to `active`.*

---

## Orphan pages — no inbound links

```dataview
TABLE dateformat(created, "MMM dd, yyyy HH:mm:ss") AS "Created", status
FROM "wiki"
WHERE orphan = true
SORT created DESC
```

*These pages exist but nothing links to them.
Orphan status is set by `synthadoc lint run` — run it first to populate this list.
Add `[[page-name]]` to a related page or to [[index]].*

---

## Recently added

```dataview
TABLE dateformat(created, "MMM dd, yyyy HH:mm:ss") AS "Added", status, confidence
FROM "wiki"
WHERE file.name != "index" AND file.name != "dashboard" AND file.name != "purpose"
SORT created DESC
LIMIT 10
```
