---
name: url
version: "1.0"
description: Fetch and extract text from web URLs
entry:
  script: scripts/main.py
  class: UrlSkill
triggers:
  extensions:
    - "https://"
    - "http://"
  intents:
    - "fetch url"
    - "web page"
    - "website"
requires:
  - httpx
  - beautifulsoup4
author: axoviq.com
license: AGPL-3.0-or-later
---

# URL Skill

Fetches a web URL using `httpx`, strips navigation/script/style tags with
`BeautifulSoup`, and returns clean body text.

## When this skill is used

- Source starts with `https://` or `http://`
- User intent contains: `fetch url`, `web page`, `website`
