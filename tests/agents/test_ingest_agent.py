# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import hashlib
import pytest
import aiosqlite
from unittest.mock import AsyncMock
from synthadoc.agents.ingest_agent import IngestAgent, IngestResult, _slugify
from synthadoc.providers.base import CompletionResponse
from synthadoc.storage.wiki import WikiStorage
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
async def test_new_page_is_orphan(tmp_wiki, mock_provider):
    """New pages created by ingest must NOT be added to index.md (they start as orphans)."""
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
    # New page must NOT appear in index.md — it is an orphan until manually linked
    assert f"[[{slug}]]" not in index_text


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
