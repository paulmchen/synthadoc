# YouTube Executive Summary Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** When a YouTube video is ingested, the wiki page opens with a concise executive summary (what the video is about, topics covered, key takeaway), followed by the full timestamped transcript.

**Architecture:** `YoutubeSkill` accepts an optional LLM provider at construction time. When the provider is present, `extract()` runs a single summary LLM call after fetching the transcript and returns pre-structured page content. `IngestAgent` detects the `has_summary` metadata flag and uses the skill's structured text as the authoritative page body — the decision LLM still decides create/update/flag and generates the slug and wikilinks, but its `page_content` / `update_content` fields are ignored.

**Tech Stack:** `youtube-transcript-api`, existing `LLMProvider` interface, regex-based CJK language detection

---

## Design Detail

### Page structure (output)

```markdown
## Executive Summary

{summary — 200 words max for Latin-script content, 400 words for CJK}

## Transcript

[0:00] caption text [0:05] more text …
```

The YAML front matter (title, tags, status, sources, created) is written by `WikiStorage` as today — unchanged.

### Summary prompt

```
Summarise this YouTube video transcript for a knowledge wiki.
Write no more than {limit} words.
- One or two sentences: what the video is about
- Bullet list: main topics covered
- One sentence: key takeaway

Markdown bullets only. No headings. No filler phrases.

Transcript:
{transcript[:6000]}
```

### Language detection

Count CJK characters (Unicode blocks U+4E00–U+9FFF, U+3040–U+309F, U+30A0–U+30FF, U+AC00–U+D7AF) in the transcript. If they exceed 10 % of total characters → `limit = 400`; otherwise `limit = 200`. No external library — a single `re.findall` count.

### Provider injection

`IngestAgent` passes the provider through `SkillAgent`'s `skill_kwargs`:

```python
self._skill_agent = SkillAgent(skill_kwargs={
    "url": {"fetch_timeout": fetch_timeout},
    "youtube": {"provider": self._provider},
})
```

`YoutubeSkill.__init__` signature: `def __init__(self, provider=None)`.

### `has_summary` flag

When the summary LLM call succeeds, `ExtractedContent` returns:
- `text` = `"## Executive Summary\n\n{summary}\n\n## Transcript\n\n{transcript}"`
- `metadata["has_summary"] = True`
- `metadata["video_id"]` = as before

### `IngestAgent` create/update paths

When `metadata.get("has_summary")` is `True`:
- **create**: use `extracted.text` as the page body; ignore decision LLM's `page_content`
- **update**: append `extracted.text` as a new section; ignore decision LLM's `update_content`
- Decision LLM still runs for action, target slug, and wikilinks

### Error handling

- Summary LLM call raises → log warning, fall back to raw transcript only (`has_summary` not set; existing behaviour unchanged)
- No captions / private video → existing graceful skip, unchanged
- Provider not injected (e.g. standalone skill tests) → no summary; raw transcript returned as today

### External docs to update

- `README.md` — add a sentence noting YouTube pages include an executive summary
- `docs/user-quick-start-guide.md` — update Step 10 to describe the summary + transcript page structure
- `docs/design.md` — update the YouTube skill description in the skills table

No Python filenames or class names in any user-facing document.

### Tests

- **`test_youtube_skill.py`**
  - `test_extract_with_provider_includes_executive_summary` — mocked provider; returned text starts with `## Executive Summary`
  - `test_extract_with_provider_includes_transcript_section` — `## Transcript` section present and contains `[MM:SS]` entries
  - `test_extract_without_provider_returns_raw_transcript` — provider=None; no `## Executive Summary` in text; `has_summary` not in metadata
  - `test_summary_language_limit_cjk` — CJK transcript → prompt contains word limit 400
  - `test_summary_language_limit_latin` — Latin transcript → prompt contains word limit 200
  - `test_extract_summary_llm_failure_falls_back` — LLM raises → returns raw transcript without `has_summary`

- **`test_ingest_agent.py`**
  - `test_youtube_has_summary_uses_skill_body_not_llm_page_content` — `has_summary=True`; page body equals skill's structured text, not decision LLM's `page_content`
  - `test_youtube_no_summary_falls_back_to_existing_behaviour` — `has_summary` absent; existing create flow unchanged
