# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import hashlib
import pytest
import aiosqlite
from unittest.mock import AsyncMock
from synthadoc.agents.ingest_agent import IngestAgent, IngestResult, _slugify, _coerce_str_list
from synthadoc.providers.base import CompletionResponse
from synthadoc.storage.wiki import WikiStorage, WikiPage
from synthadoc.storage.search import HybridSearch
from synthadoc.storage.log import LogWriter, AuditDB
from synthadoc.core.cache import CacheManager


# --- _slugify unit tests ---

def test_slugify_ascii():
    assert _slugify("Alan Turing") == "alan-turing"

def test_slugify_accented():
    assert _slugify("Café au Lait") == "cafe-au-lait"

def test_slugify_chinese():
    slug = _slugify("人工智能")
    assert slug == "人工智能"
    assert len(slug) > 0

def test_slugify_mixed_cjk_ascii():
    slug = _slugify("AI 人工智能 History")
    assert "人工智能" in slug
    assert "ai" in slug
    assert "history" in slug

def test_slugify_pure_symbols_returns_hash():
    slug = _slugify("!!! ???")
    assert slug.startswith("page-")
    assert len(slug) > 5


@pytest.fixture
def mock_provider():
    """Provider that cycles: entity response, then decision response (repeating)."""
    p = AsyncMock()
    _entity = CompletionResponse(
        text='{"entities":["AI","safety"],"concepts":["alignment"],"tags":["ai"]}',
        input_tokens=100, output_tokens=50,
    )
    _decision = CompletionResponse(
        text='{"action":"create","target":"","new_slug":"ai-safety","update_content":""}',
        input_tokens=100, output_tokens=50,
    )
    # side_effect as iterator: entity, decision, entity, decision, ...
    import itertools
    p.complete.side_effect = itertools.cycle([_entity, _decision])
    return p


@pytest.mark.asyncio
async def test_ingest_creates_page(tmp_wiki, mock_provider):
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()

    source = tmp_wiki / "raw_sources" / "test.md"
    source.write_text("# AI Safety\nAlignment is important.", encoding="utf-8")

    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)
    result = await agent.ingest(str(source))
    assert isinstance(result, IngestResult)
    assert not result.skipped
    assert result.pages_created


@pytest.mark.asyncio
async def test_ingest_skips_duplicate(tmp_wiki, mock_provider):
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()

    source = tmp_wiki / "raw_sources" / "dup.md"
    source.write_text("# Duplicate\nContent.", encoding="utf-8")

    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)
    await agent.ingest(str(source))
    result2 = await agent.ingest(str(source))
    assert result2.skipped is True


@pytest.mark.asyncio
async def test_ingest_nonexistent_path_raises(tmp_wiki, mock_provider):
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()
    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)
    with pytest.raises(FileNotFoundError):
        await agent.ingest("/tmp/does-not-exist-abc123.pdf")


@pytest.mark.asyncio
async def test_ingest_zero_byte_file_raises(tmp_wiki, mock_provider):
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()
    empty = tmp_wiki / "raw_sources" / "empty.md"
    empty.write_bytes(b"")
    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)
    with pytest.raises(ValueError, match="empty"):
        await agent.ingest(str(empty))


@pytest.mark.asyncio
async def test_force_busts_cache(tmp_wiki, mock_provider):
    """force=True must call the LLM even when a cached response exists."""
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()

    source = tmp_wiki / "raw_sources" / "bust.md"
    source.write_text("# Force bust test\nContent.", encoding="utf-8")

    import itertools
    _entity = CompletionResponse(text='{"entities":[],"concepts":[],"tags":[]}',
                                 input_tokens=100, output_tokens=50)
    _decision = CompletionResponse(
        text='{"action":"create","target":"","new_slug":"force-bust-test","update_content":""}',
        input_tokens=100, output_tokens=50)
    mock_provider.complete.side_effect = itertools.cycle([_entity, _decision])

    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)

    # First ingest — populates cache; 2 LLM calls (extract + decision)
    await agent.ingest(str(source))
    calls_after_first = mock_provider.complete.call_count

    # Second ingest without force — should use cache, no new LLM calls
    await agent.ingest(str(source), force=True)  # force=True skips dedup
    # Without bust_cache the count would stay the same; with bust_cache it increases
    await agent.ingest(str(source), force=True, bust_cache=True)
    assert mock_provider.complete.call_count > calls_after_first


@pytest.mark.asyncio
async def test_new_page_appended_to_index(tmp_wiki, mock_provider):
    """New pages created by ingest must be appended to index.md under 'Recently Added'."""
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()

    index_content = (
        "---\ntitle: Index\ntags: [index]\nstatus: active\nconfidence: high\n"
        "created: '2026-01-01'\nsources: []\n---\n\n# Index\n\n## People\n"
    )
    (tmp_wiki / "wiki" / "index.md").write_text(index_content, encoding="utf-8")

    source = tmp_wiki / "raw_sources" / "new_topic.md"
    source.write_text("# New Topic\nBrand new content.", encoding="utf-8")

    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)
    result = await agent.ingest(str(source))

    assert result.pages_created
    index_text = (tmp_wiki / "wiki" / "index.md").read_text(encoding="utf-8")
    slug = result.pages_created[0]
    # New page must appear in index.md under 'Recently Added'
    assert f"[[{slug}]]" in index_text
    assert "## Recently Added" in index_text


@pytest.mark.asyncio
async def test_ingest_flags_contradiction(tmp_wiki):
    """When LLM returns action='flag', the target page status becomes 'contradicted'."""
    from unittest.mock import AsyncMock
    p = AsyncMock()
    import itertools
    _entity = CompletionResponse(
        text='{"entities":["compiler","Grace Hopper"],"concepts":[],"tags":["history"]}',
        input_tokens=100, output_tokens=50,
    )
    _decision = CompletionResponse(
        text='{"action":"flag","target":"grace-hopper","new_slug":"","update_content":""}',
        input_tokens=100, output_tokens=50,
    )
    p.complete.side_effect = itertools.cycle([_entity, _decision])

    store = WikiStorage(tmp_wiki / "wiki")
    # Create the target page
    from synthadoc.storage.wiki import WikiPage
    store.write_page("grace-hopper", WikiPage(
        title="Grace Hopper", tags=["biography"], content="# Grace Hopper\n\nFirst compiler.",
        status="active", confidence="high", sources=[], created="2026-01-01",
    ))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()

    source = tmp_wiki / "raw_sources" / "controversy.md"
    source.write_text("A-0 was a loader, not a compiler. FORTRAN was the first.", encoding="utf-8")

    agent = IngestAgent(provider=p, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)
    result = await agent.ingest(str(source))

    assert "grace-hopper" in result.pages_flagged
    page = store.read_page("grace-hopper")
    assert page.status == "contradicted"


@pytest.mark.asyncio
async def test_ingest_flag_ignores_skip_slugs(tmp_wiki):
    """LLM targeting a skip slug (e.g. 'index') with action='flag' must be silently ignored."""
    from unittest.mock import AsyncMock
    import itertools
    from synthadoc.agents.lint_agent import LINT_SKIP_SLUGS
    from synthadoc.storage.wiki import WikiPage
    p = AsyncMock()
    _entity = CompletionResponse(
        text='{"entities":["index"],"concepts":[],"tags":[]}',
        input_tokens=100, output_tokens=50,
    )
    _decision = CompletionResponse(
        text='{"action":"flag","target":"index","new_slug":"","update_content":""}',
        input_tokens=100, output_tokens=50,
    )
    p.complete.side_effect = itertools.cycle([_entity, _decision])

    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("index", WikiPage(
        title="Index", tags=[], content="# Index\n\nWiki root.",
        status="active", confidence="high", sources=[],
    ))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()

    source = tmp_wiki / "raw_sources" / "rewrite.md"
    source.write_text("Completely different index content.", encoding="utf-8")

    agent = IngestAgent(provider=p, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)
    result = await agent.ingest(str(source))

    assert "index" not in result.pages_flagged
    page = store.read_page("index")
    assert page.status == "active", "skip slugs must never be set to contradicted"


@pytest.mark.asyncio
async def test_ingest_updates_existing_page(tmp_wiki):
    """When LLM returns action='update', content is appended to the target page."""
    from unittest.mock import AsyncMock
    p = AsyncMock()
    import itertools
    _entity = CompletionResponse(
        text='{"entities":["Alan Turing","Enigma"],"concepts":[],"tags":["history"]}',
        input_tokens=100, output_tokens=50,
    )
    _decision = CompletionResponse(
        text='{"action":"update","target":"alan-turing","new_slug":"","update_content":"## Enigma\\n\\nNew detail."}',
        input_tokens=100, output_tokens=50,
    )
    p.complete.side_effect = itertools.cycle([_entity, _decision])

    store = WikiStorage(tmp_wiki / "wiki")
    from synthadoc.storage.wiki import WikiPage
    store.write_page("alan-turing", WikiPage(
        title="Alan Turing", tags=["biography"], content="# Alan Turing\n\nMathematician.",
        status="active", confidence="high", sources=[], created="2026-01-01",
    ))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()

    source = tmp_wiki / "raw_sources" / "enigma.md"
    source.write_text("Turing broke Enigma at Bletchley Park.", encoding="utf-8")

    agent = IngestAgent(provider=p, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)
    result = await agent.ingest(str(source))

    assert "alan-turing" in result.pages_updated
    page = store.read_page("alan-turing")
    assert "Enigma" in page.content
    assert "New detail." in page.content


@pytest.mark.asyncio
async def test_ingest_hash_size_mismatch_warns_and_proceeds(tmp_wiki, mock_provider, caplog):
    """Hash match + size differs → log warning, treat as new source (not a skip)."""
    import logging
    from synthadoc.storage.log import AuditDB

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()
    source = tmp_wiki / "raw_sources" / "collision.md"
    source.write_text("# Collision test", encoding="utf-8")

    content = source.read_bytes()
    src_hash = hashlib.sha256(content).hexdigest()
    # Insert a record with the same hash but a different size (simulated collision)
    async with aiosqlite.connect(str(audit._path)) as db:
        await db.execute(
            "INSERT INTO ingests (source_hash, source_size, source_path, wiki_page, "
            "tokens, cost_usd, ingested_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (src_hash, len(content) + 999, "old.md", "old-page", 0, 0.0, "2026-01-01T00:00:00Z")
        )
        await db.commit()

    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)
    with caplog.at_level(logging.WARNING):
        result = await agent.ingest(str(source))
    assert not result.skipped
    assert any("collision" in r.message.lower() or "size" in r.message.lower()
               for r in caplog.records)


@pytest.mark.asyncio
async def test_purpose_md_filters_out_of_scope_source(tmp_wiki, mock_provider):
    """When purpose.md is present and LLM returns action=skip, result is skipped."""
    import itertools
    from synthadoc.providers.base import CompletionResponse

    (tmp_wiki / "wiki" / "purpose.md").write_text(
        "This wiki covers AI and machine learning only.", encoding="utf-8")

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()

    source = tmp_wiki / "raw_sources" / "cooking.md"
    source.write_text("# Pasta Recipes\nHow to make carbonara.", encoding="utf-8")

    entity_resp = CompletionResponse(
        text='{"entities":["pasta"],"concepts":["cooking"],"tags":["food"]}',
        input_tokens=50, output_tokens=20)
    skip_resp = CompletionResponse(
        text='{"reasoning":"Out of scope","action":"skip","target":"","new_slug":"","update_content":""}',
        input_tokens=50, output_tokens=20)
    mock_provider.complete.side_effect = itertools.cycle([entity_resp, skip_resp])

    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15,
                        wiki_root=tmp_wiki)
    result = await agent.ingest(str(source))
    assert result.skipped
    assert "scope" in result.skip_reason.lower()


@pytest.mark.asyncio
async def test_purpose_md_absent_does_not_break_ingest(tmp_wiki, mock_provider):
    """No purpose.md — ingest proceeds normally."""
    assert not (tmp_wiki / "wiki" / "purpose.md").exists()
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()
    source = tmp_wiki / "raw_sources" / "test.md"
    source.write_text("# AI Safety\nAlignment research.", encoding="utf-8")
    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)
    result = await agent.ingest(str(source))
    assert not result.skipped


def test_init_wiki_creates_purpose_md(tmp_path):
    from synthadoc.cli._init import init_wiki
    init_wiki(tmp_path, domain="AI Research")
    purpose = tmp_path / "wiki" / "purpose.md"
    assert purpose.exists()
    text = purpose.read_text(encoding="utf-8")
    assert "AI Research" in text


@pytest.mark.asyncio
async def test_overview_md_created_after_ingest(tmp_wiki):
    """overview.md must be written after a successful page creation."""
    import itertools
    from synthadoc.providers.base import CompletionResponse
    from unittest.mock import AsyncMock

    provider = AsyncMock()
    entity_resp = CompletionResponse(
        text='{"entities":["AI"],"tags":["ml"],"summary":"AI safety research.","relevant":true}',
        input_tokens=50, output_tokens=20)
    decision_resp = CompletionResponse(
        text='{"reasoning":"New topic","action":"create","target":"","new_slug":"ai-safety","update_content":""}',
        input_tokens=50, output_tokens=20)
    overview_resp = CompletionResponse(
        text="This wiki covers AI safety research.\n\nKey themes include alignment.",
        input_tokens=50, output_tokens=30)
    provider.complete = AsyncMock(side_effect=itertools.cycle(
        [entity_resp, decision_resp, overview_resp]))

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()

    source = tmp_wiki / "raw_sources" / "ai.md"
    source.write_text("# AI Safety\nAlignment is important.", encoding="utf-8")

    agent = IngestAgent(provider=provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)
    result = await agent.ingest(str(source))
    assert result.pages_created
    overview = tmp_wiki / "wiki" / "overview.md"
    assert overview.exists(), "overview.md should be created after page creation"
    text = overview.read_text(encoding="utf-8")
    assert "overview" in text.lower() or "wiki" in text.lower()


@pytest.mark.asyncio
async def test_overview_md_not_written_on_skip(tmp_wiki):
    """overview.md must NOT be written when ingest is skipped."""
    import itertools
    from synthadoc.providers.base import CompletionResponse
    from unittest.mock import AsyncMock

    provider = AsyncMock()
    entity_resp = CompletionResponse(
        text='{"entities":[],"tags":[],"summary":"Out of scope.","relevant":false}',
        input_tokens=10, output_tokens=5)
    skip_resp = CompletionResponse(
        text='{"action":"skip","target":"","new_slug":"","update_content":""}',
        input_tokens=10, output_tokens=5)
    provider.complete = AsyncMock(side_effect=itertools.cycle([entity_resp, skip_resp]))

    (tmp_wiki / "wiki" / "purpose.md").write_text("AI only.", encoding="utf-8")
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()

    source = tmp_wiki / "raw_sources" / "cooking.md"
    source.write_text("# Pasta\nHow to cook.", encoding="utf-8")

    agent = IngestAgent(provider=provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)
    await agent.ingest(str(source))
    assert not (tmp_wiki / "wiki" / "overview.md").exists()


@pytest.mark.asyncio
async def test_analyse_returns_structured_result(tmp_wiki):
    """_analyse() returns entities, tags, and a summary string."""
    from synthadoc.providers.base import CompletionResponse
    from unittest.mock import AsyncMock

    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=CompletionResponse(
        text='{"entities":["AI"],"tags":["ml"],"summary":"This source discusses AI safety.","relevant":true}',
        input_tokens=50, output_tokens=20))

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()

    agent = IngestAgent(provider=provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)
    result = await agent._analyse("AI safety content here", bust_cache=True)
    assert "entities" in result
    assert "summary" in result
    assert isinstance(result["summary"], str)


@pytest.mark.asyncio
async def test_analyse_is_cached_on_second_call(tmp_wiki):
    """Second call with same text must hit cache with 0 additional LLM calls."""
    from synthadoc.providers.base import CompletionResponse
    from unittest.mock import AsyncMock

    call_count = 0

    async def counting_complete(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return CompletionResponse(
            text='{"entities":["X"],"tags":[],"summary":"Test.","relevant":true}',
            input_tokens=10, output_tokens=5)

    provider = AsyncMock()
    provider.complete = AsyncMock(side_effect=counting_complete)

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()

    agent = IngestAgent(provider=provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)
    await agent._analyse("some text", bust_cache=False)
    first_calls = call_count
    await agent._analyse("some text", bust_cache=False)
    assert call_count == first_calls  # second call hits cache


@pytest.mark.asyncio
async def test_ingest_uses_page_content_for_new_pages(tmp_wiki):
    """When decision includes page_content, new page body uses it (not raw source text)."""
    import itertools
    from unittest.mock import AsyncMock
    from synthadoc.providers.base import CompletionResponse

    analyse_resp = CompletionResponse(
        text='{"entities":["Ada Lovelace"],"tags":["computing"],"summary":"Ada Lovelace was the first programmer.","relevant":true}',
        input_tokens=50, output_tokens=20)
    decision_resp = CompletionResponse(
        text='{"reasoning":"new topic","action":"create","target":"","new_slug":"ada-lovelace",'
             '"update_content":"","page_content":"# Ada Lovelace\\n\\nAda Lovelace (1815-1852) '
             'is widely regarded as the first computer programmer. She collaborated with '
             '[[charles-babbage]] on the [[analytical-engine]]."}',
        input_tokens=80, output_tokens=40)

    provider = AsyncMock()
    provider.complete = AsyncMock(side_effect=itertools.cycle([analyse_resp, decision_resp]))

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()

    source = tmp_wiki / "raw_sources" / "ada.md"
    source.write_text("Ada Lovelace raw text", encoding="utf-8")

    from unittest.mock import patch
    agent = IngestAgent(provider=provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)
    with patch.object(IngestAgent, "_update_overview", AsyncMock()):
        result = await agent.ingest(str(source))

    assert "ada-lovelace" in result.pages_created
    page = store.read_page("ada-lovelace")
    assert "[[charles-babbage]]" in page.content
    assert "[[analytical-engine]]" in page.content
    assert "Ada Lovelace raw text" not in page.content  # raw text not used


@pytest.mark.asyncio
async def test_ingest_preserves_wikilinks_in_update_content(tmp_wiki):
    """update_content from decision is written to page verbatim — [[wikilinks]] preserved."""
    import itertools
    from unittest.mock import AsyncMock
    from synthadoc.providers.base import CompletionResponse

    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("alan-turing", "# Alan Turing\n\nFounder of computer science.", {})

    analyse_resp = CompletionResponse(
        text='{"entities":["Turing","Enigma"],"tags":["cryptography"],"summary":"Turing broke Enigma.","relevant":true}',
        input_tokens=50, output_tokens=20)
    decision_resp = CompletionResponse(
        text='{"reasoning":"adds info","action":"update","target":"alan-turing",'
             '"new_slug":"","update_content":"## Enigma\\n\\nTuring led the team that broke '
             'the [[enigma]] cipher at [[bletchley-park]].","page_content":""}',
        input_tokens=80, output_tokens=40)

    provider = AsyncMock()
    provider.complete = AsyncMock(side_effect=itertools.cycle([analyse_resp, decision_resp]))

    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()

    source = tmp_wiki / "raw_sources" / "enigma.md"
    source.write_text("Turing broke Enigma at Bletchley Park.", encoding="utf-8")

    from unittest.mock import patch
    agent = IngestAgent(provider=provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)
    with patch.object(IngestAgent, "_update_overview", AsyncMock()):
        result = await agent.ingest(str(source))

    assert "alan-turing" in result.pages_updated
    page = store.read_page("alan-turing")
    assert "[[enigma]]" in page.content
    assert "[[bletchley-park]]" in page.content


# ── _coerce_str_list ──────────────────────────────────────────────────────────

def test_coerce_str_list_plain_strings_unchanged():
    assert _coerce_str_list(["AI", "Canada"]) == ["AI", "Canada"]


def test_coerce_str_list_dict_entities_extracted():
    """Some LLMs return entities as dicts with a 'name' field."""
    result = _coerce_str_list([
        {"name": "Canada", "type": "location"},
        {"name": "Llama 3", "type": "model"},
    ])
    assert result == ["Canada", "Llama 3"]


def test_coerce_str_list_mixed_str_and_dict():
    result = _coerce_str_list(["AI", {"name": "OpenAI", "type": "org"}, "safety"])
    assert result == ["AI", "OpenAI", "safety"]


def test_coerce_str_list_fallback_fields():
    """Falls back to 'value', 'label', 'text' if 'name' is absent."""
    assert _coerce_str_list([{"value": "machine learning"}]) == ["machine learning"]
    assert _coerce_str_list([{"label": "NLP"}]) == ["NLP"]
    assert _coerce_str_list([{"text": "deep learning"}]) == ["deep learning"]


def test_coerce_str_list_drops_empty_strings():
    assert _coerce_str_list(["", "AI", "  "]) == ["AI"]


def test_coerce_str_list_non_list_input_returns_empty():
    assert _coerce_str_list(None) == []
    assert _coerce_str_list("not a list") == []
    assert _coerce_str_list(42) == []


@pytest.mark.asyncio
async def test_analyse_coerces_dict_entities_to_strings(tmp_wiki):
    """_analyse() must return entities as strings even if the LLM returns dicts."""
    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=CompletionResponse(
        text='{"entities":[{"name":"Canada","type":"location"},{"name":"Gardening"}],'
             '"tags":[{"name":"plants"}],"summary":"Canadian gardening.","relevant":true}',
        input_tokens=40, output_tokens=15))

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()

    agent = IngestAgent(provider=provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)
    result = await agent._analyse("Canadian gardening content", bust_cache=True)

    assert all(isinstance(e, str) for e in result["entities"]), \
        f"entities must all be strings, got: {result['entities']}"
    assert all(isinstance(t, str) for t in result["tags"]), \
        f"tags must all be strings, got: {result['tags']}"
    assert "Canada" in result["entities"]
    assert "plants" in result["tags"]


@pytest.mark.asyncio
async def test_ingest_vision_path_extracts_text_from_image(tmp_wiki):
    """ImageSkill returns extracted text; IngestAgent ingests it and accounts for vision tokens."""
    import itertools
    from unittest.mock import AsyncMock, patch
    from synthadoc.providers.base import CompletionResponse

    provider = AsyncMock()
    entity_resp = CompletionResponse(
        text='{"entities":["CPU","architecture"],"tags":["hardware"],"summary":"CPU diagram.","relevant":true}',
        input_tokens=40, output_tokens=20)
    decision_resp = CompletionResponse(
        text='{"action":"create","target":"","new_slug":"cpu-architecture","update_content":""}',
        input_tokens=50, output_tokens=25)
    provider.complete = AsyncMock(side_effect=itertools.cycle([entity_resp, decision_resp]))
    provider.supports_vision = True

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()

    img_path = tmp_wiki / "raw_sources" / "diagram.png"
    img_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    # ImageSkill now returns populated text + token counts in metadata
    from synthadoc.skills.base import ExtractedContent
    fake_extracted = ExtractedContent(
        text="A diagram showing a CPU architecture.",
        source_path=str(img_path),
        metadata={"tokens_input": 30, "tokens_output": 15},
    )

    agent = IngestAgent(provider=provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)

    with patch.object(agent._skill_agent, "extract", AsyncMock(return_value=fake_extracted)):
        with patch.object(IngestAgent, "_update_overview", AsyncMock()):
            result = await agent.ingest(str(img_path))

    assert not result.skipped
    assert result.pages_created
    # Vision tokens surfaced by the skill are tracked in the ingest result
    assert result.input_tokens >= 30
    assert result.output_tokens >= 15


@pytest.mark.asyncio
async def test_ingest_slug_collision_appends_as_update(tmp_wiki):
    """When the target slug already exists for a 'create' action, content is appended instead."""
    import itertools
    from unittest.mock import AsyncMock, patch
    from synthadoc.providers.base import CompletionResponse
    from synthadoc.storage.wiki import WikiPage

    provider = AsyncMock()
    entity_resp = CompletionResponse(
        text='{"entities":["Turing"],"tags":["history"],"summary":"About Turing.","relevant":true}',
        input_tokens=50, output_tokens=20)
    # LLM tries to create "alan-turing" but that slug already exists
    decision_resp = CompletionResponse(
        text='{"action":"create","target":"","new_slug":"alan-turing","update_content":"","page_content":"# Alan Turing\\n\\nExtra facts."}',
        input_tokens=50, output_tokens=25)
    provider.complete = AsyncMock(side_effect=itertools.cycle([entity_resp, decision_resp]))

    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("alan-turing", WikiPage(
        title="Alan Turing", tags=["biography"],
        content="# Alan Turing\n\nOriginal content.",
        status="active", confidence="high", sources=[], created="2026-01-01",
    ))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()

    source = tmp_wiki / "raw_sources" / "turing2.md"
    source.write_text("More facts about Alan Turing.", encoding="utf-8")

    agent = IngestAgent(provider=provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)
    with patch.object(IngestAgent, "_update_overview", AsyncMock()):
        result = await agent.ingest(str(source))

    # Must be recorded as an update, not a new creation (original content preserved)
    assert "alan-turing" in result.pages_updated
    assert "alan-turing" not in result.pages_created
    page = store.read_page("alan-turing")
    assert "Original content." in page.content


@pytest.mark.asyncio
async def test_no_extractable_text_produces_skip(tmp_wiki, mock_provider):
    """Empty extracted text on a create action skips with skip_reason='no extractable text'."""
    from unittest.mock import patch
    from synthadoc.skills.base import ExtractedContent

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()

    source = tmp_wiki / "raw_sources" / "blank.md"
    source.write_text("some bytes so it passes the size check", encoding="utf-8")

    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)
    fake_extracted = ExtractedContent(text="", source_path=str(source), metadata={})
    with patch.object(agent._skill_agent, "extract", AsyncMock(return_value=fake_extracted)):
        result = await agent.ingest(str(source))

    assert result.skipped is True
    assert result.skip_reason == "no extractable text"


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


@pytest.mark.asyncio
async def test_youtube_rerun_same_url_is_skipped(tmp_wiki, mock_provider):
    """Re-ingesting the same YouTube URL must be skipped (deduped by URL hash)."""
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

    url = "https://www.youtube.com/watch?v=O5nskjZ_GoI"
    mock_extracted = ExtractedContent(
        text="[0:00] Hello world.",
        source_path=url,
        metadata={"url": url, "video_id": "O5nskjZ_GoI"},
    )

    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)

    with patch.object(agent._skill_agent, "extract", return_value=mock_extracted):
        first = await agent.ingest(url)
        second = await agent.ingest(url)

    assert not first.skipped, "first ingest must create or update a page"
    assert first.pages_created or first.pages_updated
    assert second.skipped, "second ingest of same URL must be skipped"
    assert second.skip_reason == "already ingested"


@pytest.mark.asyncio
async def test_youtube_rerun_allowed_after_page_deleted(tmp_wiki, mock_provider):
    """Re-ingesting a URL must succeed (not be skipped) if the wiki page was deleted."""
    from unittest.mock import patch
    from synthadoc.skills.base import ExtractedContent

    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()

    url = "https://www.youtube.com/watch?v=O5nskjZ_GoI"
    mock_extracted = ExtractedContent(
        text="[0:00] Hello world.",
        source_path=url,
        metadata={"url": url, "video_id": "O5nskjZ_GoI"},
    )

    agent = IngestAgent(provider=mock_provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache,
                        max_pages=15, wiki_root=tmp_wiki)

    with patch.object(agent._skill_agent, "extract", return_value=mock_extracted):
        first = await agent.ingest(url)

    assert first.pages_created, "first ingest must create a page"
    slug = first.pages_created[0]

    # Simulate user deleting the page from the UI
    (tmp_wiki / "wiki" / f"{slug}.md").unlink()

    with patch.object(agent._skill_agent, "extract", return_value=mock_extracted):
        third = await agent.ingest(url)

    assert not third.skipped, "re-ingest after page deletion must not be skipped"


# ── CJK (Chinese / Japanese / Korean) coverage ───────────────────────────────

@pytest.mark.asyncio
async def test_ingest_cjk_source_creates_page(tmp_wiki):
    """Source file with Chinese content → page created with CJK slug and content preserved."""
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()

    source = tmp_wiki / "raw_sources" / "量子计算.md"
    source.write_text(
        "# 量子计算\n量子计算是利用量子力学原理进行信息处理的技术。量子比特可以同时处于0和1的叠加态。",
        encoding="utf-8",
    )
    import itertools
    provider = AsyncMock()
    provider.complete.side_effect = itertools.cycle([
        CompletionResponse(
            text='{"entities":["量子计算","量子比特"],"concepts":["量子叠加"],"tags":["量子计算","技术"]}',
            input_tokens=100, output_tokens=50,
        ),
        CompletionResponse(
            text='{"reasoning":"新主题","action":"create","target":"","new_slug":"量子计算","update_content":"","page_content":""}',
            input_tokens=100, output_tokens=50,
        ),
    ])
    agent = IngestAgent(provider=provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)
    result = await agent.ingest(str(source))

    assert not result.skipped
    assert result.pages_created
    page = store.read_page("量子计算")
    assert page is not None
    assert "量子" in page.content
    assert "量子计算" in page.title or "量子计算" in result.pages_created[0]


@pytest.mark.asyncio
async def test_ingest_cjk_page_update_appends_content(tmp_wiki):
    """Ingest with action=update appends a CJK section to an existing CJK page."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("人工智能", WikiPage(
        title="人工智能", tags=["技术"],
        content="# 人工智能\n人工智能是模拟人类思维的技术。",
        status="active", confidence="medium", sources=[],
    ))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()

    source = tmp_wiki / "raw_sources" / "ml-update.md"
    source.write_text("机器学习是人工智能的重要子领域。", encoding="utf-8")

    import itertools
    provider = AsyncMock()
    provider.complete.side_effect = itertools.cycle([
        CompletionResponse(
            text='{"entities":["机器学习","人工智能"],"concepts":["监督学习"],"tags":["人工智能"]}',
            input_tokens=100, output_tokens=50,
        ),
        CompletionResponse(
            text='{"reasoning":"补充信息","action":"update","target":"人工智能","new_slug":"","update_content":"## 机器学习\\n机器学习是人工智能的重要分支，包括监督学习和无监督学习。","page_content":""}',
            input_tokens=100, output_tokens=50,
        ),
    ])
    agent = IngestAgent(provider=provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)
    result = await agent.ingest(str(source))

    assert "人工智能" in result.pages_updated
    page = store.read_page("人工智能")
    assert "机器学习" in page.content
    assert "人工智能" in page.content   # original content preserved


@pytest.mark.asyncio
async def test_ingest_cjk_tags_stored_in_page(tmp_wiki):
    """CJK tags from the entity extraction response are stored in the created WikiPage."""
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    log = LogWriter(tmp_wiki / "wiki" / "log.md")
    audit = AuditDB(tmp_wiki / ".synthadoc" / "audit.db")
    await audit.init()
    cache = CacheManager(tmp_wiki / ".synthadoc" / "cache.db")
    await cache.init()

    source = tmp_wiki / "raw_sources" / "深度学习.md"
    source.write_text("深度学习通过多层神经网络学习数据特征。", encoding="utf-8")

    import itertools
    provider = AsyncMock()
    provider.complete.side_effect = itertools.cycle([
        CompletionResponse(
            text='{"entities":["深度学习","神经网络"],"concepts":["反向传播"],"tags":["深度学习","机器学习","人工智能"]}',
            input_tokens=100, output_tokens=50,
        ),
        CompletionResponse(
            text='{"reasoning":"新主题","action":"create","target":"","new_slug":"深度学习","update_content":"","page_content":""}',
            input_tokens=100, output_tokens=50,
        ),
    ])
    agent = IngestAgent(provider=provider, store=store, search=search,
                        log_writer=log, audit_db=audit, cache=cache, max_pages=15)
    await agent.ingest(str(source))

    page = store.read_page("深度学习")
    assert page is not None
    assert "深度学习" in page.tags or "机器学习" in page.tags
