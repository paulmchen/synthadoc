# YouTube Executive Summary Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** When a YouTube video is ingested, the wiki page opens with a concise executive summary (what the video is about, topics covered, key takeaway), followed by the full timestamped transcript.

**Architecture:** `YoutubeSkill` accepts an optional LLM provider at construction time. When present, `extract()` runs one summary LLM call after fetching the transcript and returns structured content (`## Executive Summary` + `## Transcript`). `IngestAgent` detects the `has_summary` metadata flag and uses the skill's text as the authoritative page body — the decision LLM still runs for create/update/flag and slug generation, but its `page_content` / `update_content` fields are ignored.

**Tech Stack:** Existing `LLMProvider` interface (`synthadoc/providers/base.py`), `re` for CJK detection, `youtube-transcript-api` (unchanged)

---

### Task 1: CJK language detection + summary prompt constant

**Files:**
- Modify: `synthadoc/skills/youtube/scripts/main.py`
- Test: `tests/skills/test_youtube_skill.py`

**Step 1: Write the failing tests**

Add to `tests/skills/test_youtube_skill.py`:

```python
def test_is_cjk_dominant_true():
    from synthadoc.skills.youtube.scripts.main import _is_cjk_dominant
    assert _is_cjk_dominant("这是一段中文文字，用于测试CJK字符检测功能。") is True


def test_is_cjk_dominant_false():
    from synthadoc.skills.youtube.scripts.main import _is_cjk_dominant
    assert _is_cjk_dominant("This is plain English text with no CJK characters.") is False


def test_is_cjk_dominant_mixed_under_threshold():
    from synthadoc.skills.youtube.scripts.main import _is_cjk_dominant
    # 1 CJK char in 100 chars total = 1% — below 10% threshold
    text = "A" * 99 + "中"
    assert _is_cjk_dominant(text) is False


def test_is_cjk_dominant_empty_string():
    from synthadoc.skills.youtube.scripts.main import _is_cjk_dominant
    assert _is_cjk_dominant("") is False
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/skills/test_youtube_skill.py::test_is_cjk_dominant_true tests/skills/test_youtube_skill.py::test_is_cjk_dominant_false tests/skills/test_youtube_skill.py::test_is_cjk_dominant_mixed_under_threshold tests/skills/test_youtube_skill.py::test_is_cjk_dominant_empty_string -v
```

Expected: FAIL with `ImportError: cannot import name '_is_cjk_dominant'`

**Step 3: Add constants and helper to `main.py`**

Add after the existing imports (after `from synthadoc.skills.base import ...`) and before `logger = ...`:

```python
import re

_CJK_RE = re.compile(
    r'[一-鿿぀-ゟ゠-ヿ가-힯]'
)

_YOUTUBE_SUMMARY_PROMPT = (
    "Summarise this YouTube video transcript for a knowledge wiki.\n"
    "Write no more than {limit} words.\n"
    "- One or two sentences: what the video is about\n"
    "- Bullet list: main topics covered\n"
    "- One sentence: key takeaway\n\n"
    "Markdown bullets only. No headings. No filler phrases.\n\n"
    "Transcript:\n{transcript}"
)


def _is_cjk_dominant(text: str) -> bool:
    if not text:
        return False
    return len(_CJK_RE.findall(text)) / len(text) > 0.10
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/skills/test_youtube_skill.py::test_is_cjk_dominant_true tests/skills/test_youtube_skill.py::test_is_cjk_dominant_false tests/skills/test_youtube_skill.py::test_is_cjk_dominant_mixed_under_threshold tests/skills/test_youtube_skill.py::test_is_cjk_dominant_empty_string -v
```

Expected: 4 PASSED

**Step 5: Commit**

```bash
git add synthadoc/skills/youtube/scripts/main.py tests/skills/test_youtube_skill.py
git commit -m "feat: add CJK language detection and summary prompt constant to YouTube skill"
```

---

### Task 2: `YoutubeSkill` — provider injection and summary LLM call

**Files:**
- Modify: `synthadoc/skills/youtube/scripts/main.py`
- Test: `tests/skills/test_youtube_skill.py`

**Step 1: Write the failing tests**

Add to `tests/skills/test_youtube_skill.py`:

```python
@pytest.mark.asyncio
async def test_extract_without_provider_returns_raw_transcript():
    """Without a provider, extract() returns raw transcript — existing behaviour."""
    skill = _load_skill()  # no provider
    with patch("synthadoc.skills.youtube.scripts.main.asyncio.to_thread",
               new=AsyncMock(return_value=_fake_transcript())):
        result = await skill.extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert "## Executive Summary" not in result.text
    assert result.metadata.get("has_summary") is not True


@pytest.mark.asyncio
async def test_extract_with_provider_includes_executive_summary():
    """With a provider, extract() returns text starting with ## Executive Summary."""
    from synthadoc.providers.base import CompletionResponse
    from synthadoc.skills.youtube.scripts.main import YoutubeSkill

    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text="A video about computing history.\n- Topic one\n- Topic two\nKey takeaway: history matters.",
        input_tokens=100, output_tokens=50,
    )
    skill = YoutubeSkill(provider=provider)
    with patch("synthadoc.skills.youtube.scripts.main.asyncio.to_thread",
               new=AsyncMock(return_value=_fake_transcript())):
        result = await skill.extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert result.text.startswith("## Executive Summary")


@pytest.mark.asyncio
async def test_extract_with_provider_has_summary_metadata():
    """With a provider, metadata must include has_summary=True."""
    from synthadoc.providers.base import CompletionResponse
    from synthadoc.skills.youtube.scripts.main import YoutubeSkill

    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text="Summary text.", input_tokens=10, output_tokens=10,
    )
    skill = YoutubeSkill(provider=provider)
    with patch("synthadoc.skills.youtube.scripts.main.asyncio.to_thread",
               new=AsyncMock(return_value=_fake_transcript())):
        result = await skill.extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert result.metadata.get("has_summary") is True


@pytest.mark.asyncio
async def test_extract_with_provider_includes_transcript_section():
    """Structured output must include ## Transcript section with [MM:SS] entries."""
    from synthadoc.providers.base import CompletionResponse
    from synthadoc.skills.youtube.scripts.main import YoutubeSkill

    provider = AsyncMock()
    provider.complete.return_value = CompletionResponse(
        text="Summary text.", input_tokens=10, output_tokens=10,
    )
    skill = YoutubeSkill(provider=provider)
    with patch("synthadoc.skills.youtube.scripts.main.asyncio.to_thread",
               new=AsyncMock(return_value=_fake_transcript())):
        result = await skill.extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert "## Transcript" in result.text
    assert "[0:00]" in result.text


@pytest.mark.asyncio
async def test_extract_summary_llm_failure_falls_back():
    """If the summary LLM call raises, extract() falls back to raw transcript."""
    from synthadoc.skills.youtube.scripts.main import YoutubeSkill

    provider = AsyncMock()
    provider.complete.side_effect = RuntimeError("LLM unavailable")
    skill = YoutubeSkill(provider=provider)
    with patch("synthadoc.skills.youtube.scripts.main.asyncio.to_thread",
               new=AsyncMock(return_value=_fake_transcript())):
        result = await skill.extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert "## Executive Summary" not in result.text
    assert result.metadata.get("has_summary") is not True


@pytest.mark.asyncio
async def test_summary_uses_limit_200_for_latin():
    """Latin transcript → prompt must contain '200 words'."""
    from synthadoc.providers.base import CompletionResponse
    from synthadoc.skills.youtube.scripts.main import YoutubeSkill

    provider = AsyncMock()
    captured_prompt = []

    async def capture(messages, **kwargs):
        captured_prompt.append(messages[0].content)
        return CompletionResponse(text="ok", input_tokens=5, output_tokens=5)

    provider.complete.side_effect = capture
    skill = YoutubeSkill(provider=provider)
    with patch("synthadoc.skills.youtube.scripts.main.asyncio.to_thread",
               new=AsyncMock(return_value=_fake_transcript())):
        await skill.extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert "200 words" in captured_prompt[0]


@pytest.mark.asyncio
async def test_summary_uses_limit_400_for_cjk():
    """CJK transcript → prompt must contain '400 words'."""
    from types import SimpleNamespace
    from synthadoc.providers.base import CompletionResponse
    from synthadoc.skills.youtube.scripts.main import YoutubeSkill

    provider = AsyncMock()
    captured_prompt = []

    async def capture(messages, **kwargs):
        captured_prompt.append(messages[0].content)
        return CompletionResponse(text="好的", input_tokens=5, output_tokens=5)

    provider.complete.side_effect = capture

    cjk_snippets = [
        SimpleNamespace(text="这是关于计算机历史的视频。晶体管的发明改变了世界。", start=0.0, duration=5.0),
        SimpleNamespace(text="摩尔定律预测了集成电路上晶体管数量的增长趋势。", start=5.0, duration=5.0),
    ]
    skill = YoutubeSkill(provider=provider)
    with patch("synthadoc.skills.youtube.scripts.main.asyncio.to_thread",
               new=AsyncMock(return_value=cjk_snippets)):
        await skill.extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert "400 words" in captured_prompt[0]
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/skills/test_youtube_skill.py::test_extract_without_provider_returns_raw_transcript tests/skills/test_youtube_skill.py::test_extract_with_provider_includes_executive_summary tests/skills/test_youtube_skill.py::test_extract_with_provider_has_summary_metadata tests/skills/test_youtube_skill.py::test_extract_with_provider_includes_transcript_section tests/skills/test_youtube_skill.py::test_extract_summary_llm_failure_falls_back tests/skills/test_youtube_skill.py::test_summary_uses_limit_200_for_latin tests/skills/test_youtube_skill.py::test_summary_uses_limit_400_for_cjk -v
```

Expected: Most FAIL. At minimum, provider-related tests fail.

**Step 3: Update `YoutubeSkill` in `main.py`**

Replace the `YoutubeSkill` class with:

```python
class YoutubeSkill(BaseSkill):
    meta = SkillMeta(
        name="youtube",
        description="Extract transcripts from YouTube videos via the YouTube caption system",
        extensions=["https://www.youtube.com/", "https://youtu.be/"],
    )

    def __init__(self, provider=None) -> None:
        super().__init__()
        self._provider = provider

    async def _summarise(self, transcript_text: str) -> str:
        limit = 400 if _is_cjk_dominant(transcript_text) else 200
        prompt = _YOUTUBE_SUMMARY_PROMPT.format(
            limit=limit,
            transcript=transcript_text[:6000],
        )
        from synthadoc.providers.base import Message
        resp = await self._provider.complete(
            messages=[Message(role="user", content=prompt)],
            temperature=0.3,
            max_tokens=512,
        )
        return resp.text.strip()

    async def extract(self, source: str) -> ExtractedContent:
        from youtube_transcript_api import (
            YouTubeTranscriptApi,
            NoTranscriptFound,
            VideoUnavailable,
        )

        video_id = _extract_video_id(source)
        if not video_id:
            logger.warning("youtube: could not parse video ID from %s — skipping", source)
            return ExtractedContent(text="", source_path=source, metadata={"url": source})

        api = YouTubeTranscriptApi()
        try:
            fetched = await asyncio.to_thread(api.fetch, video_id)
        except NoTranscriptFound:
            logger.warning(
                "youtube: no captions available for %s — "
                "enable auto-generated captions or choose a different video",
                source,
            )
            return ExtractedContent(
                text="",
                source_path=source,
                metadata={"url": source, "video_id": video_id, "no_transcript": True},
            )
        except VideoUnavailable:
            logger.warning(
                "youtube: video unavailable (private or deleted): %s — skipping", source
            )
            return ExtractedContent(
                text="", source_path=source, metadata={"url": source}
            )

        transcript_text = " ".join(
            f"[{_format_timestamp(snippet.start)}] {snippet.text}" for snippet in fetched
        )

        if self._provider is not None:
            try:
                summary = await self._summarise(transcript_text)
                structured = (
                    f"## Executive Summary\n\n{summary}\n\n"
                    f"## Transcript\n\n{transcript_text}"
                )
                return ExtractedContent(
                    text=structured,
                    source_path=source,
                    metadata={"url": source, "video_id": video_id, "has_summary": True},
                )
            except Exception:
                logger.warning(
                    "youtube: summary LLM call failed for %s — returning raw transcript", source
                )

        return ExtractedContent(
            text=transcript_text,
            source_path=source,
            metadata={"url": source, "video_id": video_id},
        )
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/skills/test_youtube_skill.py -v
```

Expected: All tests PASS (including existing ones).

**Step 5: Commit**

```bash
git add synthadoc/skills/youtube/scripts/main.py tests/skills/test_youtube_skill.py
git commit -m "feat: YouTube skill generates executive summary when LLM provider is injected"
```

---

### Task 3: `IngestAgent` — wire provider + honour `has_summary` flag

**Files:**
- Modify: `synthadoc/agents/ingest_agent.py` (lines ~178, ~447–485)
- Test: `tests/agents/test_ingest_agent.py`

**Step 1: Write the failing tests**

Add to `tests/agents/test_ingest_agent.py`:

```python
@pytest.mark.asyncio
async def test_youtube_has_summary_uses_skill_body(tmp_wiki, mock_provider):
    """When has_summary=True, page body must equal extracted.text, not LLM page_content."""
    from unittest.mock import patch
    from synthadoc.skills.base import ExtractedContent
    from synthadoc.storage.wiki import WikiStorage
    from synthadoc.storage.search import HybridSearch
    from synthadoc.storage.log import LogWriter, AuditDB
    from synthadoc.core.cache import CacheManager

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()

    skill_text = (
        "## Executive Summary\n\n"
        "A video about computing history.\n"
        "- Topic: Hollerith machine\n"
        "- Topic: Early programmers\n"
        "Key takeaway: computing began with mechanical tabulation.\n\n"
        "## Transcript\n\n"
        "[0:00] Hello world. [0:02] This is a test."
    )
    mock_extracted = ExtractedContent(
        text=skill_text,
        source_path="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        metadata={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                  "video_id": "dQw4w9WgXcQ", "has_summary": True},
    )

    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)

    with patch.object(agent._skill_agent, "extract", return_value=mock_extracted):
        result = await agent.ingest("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert result.pages_created or result.pages_updated
    slug = (result.pages_created + result.pages_updated)[0]
    page = store.read_page(slug)
    assert page is not None
    assert "## Executive Summary" in page.content
    assert "## Transcript" in page.content
    assert "[0:00]" in page.content


@pytest.mark.asyncio
async def test_youtube_no_summary_falls_back_to_existing_flow(tmp_wiki, mock_provider):
    """Without has_summary, page creation uses the existing LLM synthesis flow."""
    from unittest.mock import patch
    from synthadoc.skills.base import ExtractedContent
    from synthadoc.storage.wiki import WikiStorage
    from synthadoc.storage.search import HybridSearch
    from synthadoc.storage.log import LogWriter, AuditDB
    from synthadoc.core.cache import CacheManager

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()

    mock_extracted = ExtractedContent(
        text="[0:00] Hello world. [0:02] This is a test.",
        source_path="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        metadata={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                  "video_id": "dQw4w9WgXcQ"},
    )

    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)

    with patch.object(agent._skill_agent, "extract", return_value=mock_extracted):
        result = await agent.ingest("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert result.pages_created or result.pages_updated
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/agents/test_ingest_agent.py::test_youtube_has_summary_uses_skill_body tests/agents/test_ingest_agent.py::test_youtube_no_summary_falls_back_to_existing_flow -v
```

Expected: `test_youtube_has_summary_uses_skill_body` FAILS (page content won't contain `## Executive Summary` yet).

**Step 3: Wire provider into `skill_kwargs` in `IngestAgent.__init__`**

In `synthadoc/agents/ingest_agent.py`, find (around line 178):

```python
self._skill_agent = SkillAgent(skill_kwargs={"url": {"fetch_timeout": fetch_timeout}})
```

Replace with:

```python
self._skill_agent = SkillAgent(skill_kwargs={
    "url": {"fetch_timeout": fetch_timeout},
    "youtube": {"provider": self._provider},
})
```

**Step 4: Update the create path to honour `has_summary`**

In `synthadoc/agents/ingest_agent.py`, inside the `else:  # "create" or fallback` block, find:

```python
body = page_content.strip() if page_content.strip() else f"# {title}\n\n{text[:4000]}"
```

Replace with:

```python
if extracted.metadata.get("has_summary"):
    body = extracted.text
elif page_content.strip():
    body = page_content.strip()
else:
    body = f"# {title}\n\n{text[:4000]}"
```

**Step 5: Update the slug-collision update path to honour `has_summary`**

In the same `else` block, in the `if self._store.page_exists(slug):` branch, find:

```python
            section = f"## From {p.name}\n\n{text[:1500]}"
```

Replace with:

```python
            if extracted.metadata.get("has_summary"):
                section = extracted.text
            else:
                section = f"## From {p.name}\n\n{text[:1500]}"
```

**Step 6: Run tests to verify they pass**

```bash
pytest tests/agents/test_ingest_agent.py::test_youtube_has_summary_uses_skill_body tests/agents/test_ingest_agent.py::test_youtube_no_summary_falls_back_to_existing_flow -v
```

Expected: Both PASS.

**Step 7: Run full test suite**

```bash
pytest -x -q
```

Expected: All tests PASS.

**Step 8: Commit**

```bash
git add synthadoc/agents/ingest_agent.py tests/agents/test_ingest_agent.py
git commit -m "feat: IngestAgent wires provider to YouTube skill and uses skill body when has_summary=True"
```

---

### Task 4: External docs update

**Files:**
- Modify: `README.md`
- Modify: `docs/user-quick-start-guide.md`
- Modify: `docs/design.md`

No Python filenames or class names in any of these files.

**Step 1: Update `README.md`**

Find the YouTube ingest comment block (around line 526):

```
# YouTube video — transcript extracted automatically, no API key needed.
```

Add a new note paragraph immediately after the closing ` ``` ` of that code block:

```
Each YouTube wiki page opens with an **executive summary** — what the video is about,
the main topics covered, and the key takeaway — followed by the full timestamped transcript
for precise citation.
```

**Step 2: Update `docs/user-quick-start-guide.md` Step 10**

Find (around line 581):

```
Pass any YouTube URL directly — the transcript is extracted automatically from the
YouTube caption system (no API key, no audio download) and synthesized into wiki pages:
```

Replace with:

```
Pass any YouTube URL directly — the transcript is extracted automatically from the
YouTube caption system (no API key, no audio download):
```

Then add a new paragraph after the `synthadoc ingest` code block (before the `> **Captions required**` note):

```
The wiki page opens with an **executive summary** — a brief description of what the video
covers, the main topics as bullet points, and the key takeaway — so you can assess
relevance at a glance. The full timestamped transcript follows for precise cross-referencing.
```

**Step 3: Update `docs/design.md` skills table**

Find the `youtube` row (around line 417):

```
| `youtube` | ... | Extracts captions via YouTube caption system; no API key or audio download needed. Skips gracefully when no captions are available. |
```

Replace the description cell with:

```
Extracts captions via YouTube caption system; no API key or audio download needed. Generates an executive summary (what the video covers, main topics, key takeaway) followed by the full timestamped transcript. Skips gracefully when no captions are available.
```

**Step 4: Run full test suite**

```bash
pytest -x -q
```

Expected: All tests PASS.

**Step 5: Commit**

```bash
git add README.md docs/user-quick-start-guide.md docs/design.md
git commit -m "docs: document YouTube executive summary in README, quick-start guide, and design doc"
```

---

## Done

All tasks complete when:
- `pytest -x -q` passes with no failures
- `synthadoc ingest "https://www.youtube.com/watch?v=O5nskjZ_GoI" -w history-of-computing` produces a wiki page that opens with `## Executive Summary` and ends with `## Transcript`
