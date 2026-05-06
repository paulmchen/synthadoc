# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest
from synthadoc.storage.wiki import WikiStorage, WikiPage
from synthadoc.storage.search import HybridSearch


def _make_page(content: str) -> WikiPage:
    return WikiPage(title=content[:20], tags=[], content=content,
                    status="active", confidence="medium", sources=[])


def _write_page(store, slug, content):
    store.write_page(slug, WikiPage(
        title=slug.replace("-", " ").title(), tags=[],
        content=content, status="active", confidence="high", sources=[]))


def test_bm25_finds_relevant_page(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("transformers", _make_page("Transformers use self-attention mechanisms."))
    store.write_page("rlhf", _make_page("RLHF trains models with human feedback."))
    store.write_page("cnn", _make_page("CNNs use convolutional filters for images."))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    results = search.bm25_search(["attention", "transformer"], top_n=2)
    assert any(r.slug == "transformers" for r in results)


def test_returns_at_most_top_n(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    for i in range(10):
        store.write_page(f"page-{i}", _make_page(f"content about topic {i}"))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    results = search.bm25_search(["content", "topic"], top_n=3)
    assert len(results) <= 3


def test_empty_wiki_returns_empty(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    assert search.bm25_search(["anything"], top_n=5) == []


def test_bm25_finds_cjk_page(tmp_wiki):
    """Chinese character queries and documents should produce non-zero BM25 scores.
    Requires 3+ docs: BM25Okapi IDF = log((N-df+0.5)/(df+0.5)); with N=2 df=1 → log(1) = 0.
    """
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("ai-zh",  _make_page("人工智能是计算机科学的一个分支。"))
    store.write_page("other1", _make_page("Unrelated English content here."))
    store.write_page("other2", _make_page("More unrelated English text about history."))
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    results = search.bm25_search(["人工智能"], top_n=5)
    assert any(r.slug == "ai-zh" for r in results)


def test_tokenize_includes_cjk_chars():
    """Tokenizer must not drop CJK characters."""
    from synthadoc.storage.search import HybridSearch
    tokens = HybridSearch._tokenize("人工智能 AI")
    assert "人" in tokens
    assert "工" in tokens
    assert "ai" in tokens


# ── corpus cache tests ────────────────────────────────────────────────────────

def test_bm25_corpus_built_once_for_repeated_calls(tmp_wiki):
    """Corpus must only be built once — same object reused on second search."""
    store = WikiStorage(tmp_wiki / "wiki")
    _write_page(store, "chlorine", "chlorine treats algae in pools")
    _write_page(store, "ph", "pH balance is important for pools")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")

    search.bm25_search(["chlorine"], top_n=5)
    corpus_after_first = search._cached_corpus
    search.bm25_search(["pH"], top_n=5)
    assert search._cached_corpus is corpus_after_first, "corpus must not be rebuilt between searches"


def test_bm25_corpus_invalidated_after_write(tmp_wiki):
    """After invalidate_index(), corpus must be rebuilt on next search."""
    store = WikiStorage(tmp_wiki / "wiki")
    _write_page(store, "chlorine", "chlorine treats algae")
    _write_page(store, "unrelated", "the quick brown fox jumps over the lazy dog")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")

    search.bm25_search(["chlorine"], top_n=5)
    corpus_before = search._cached_corpus

    _write_page(store, "nitrogen", "nitrogen fertiliser for lawns")
    search.invalidate_index()
    # After invalidation, corpus must be None
    assert search._cached_corpus is None
    results = search.bm25_search(["nitrogen"], top_n=5)
    # Corpus rebuilt — must be a new object
    assert search._cached_corpus is not corpus_before
    assert "nitrogen" in [r.slug for r in results]


# ── performance: corpus cache behaviour ─────────────────────────────────────

def test_corpus_cache_populated_after_first_search(tmp_wiki):
    """_cached_corpus must be set (non-None) after the first bm25_search call."""
    store = WikiStorage(tmp_wiki / "wiki")
    _write_page(store, "chlorine", "chlorine treats algae in pools")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    assert search._cached_corpus is None
    search.bm25_search(["chlorine"], top_n=5)
    assert search._cached_corpus is not None


def test_corpus_built_once_for_different_queries(tmp_wiki):
    """Corpus instance must be reused across different queries without invalidation."""
    store = WikiStorage(tmp_wiki / "wiki")
    _write_page(store, "chlorine", "chlorine treats algae in pools")
    _write_page(store, "ph", "pH balance is important for pools")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")

    search.bm25_search(["chlorine"], top_n=5)
    corpus_id = id(search._cached_corpus)
    search.bm25_search(["pH balance"], top_n=5)
    assert id(search._cached_corpus) == corpus_id, "corpus must be built once, not once per query"


def test_corpus_repopulated_after_invalidation(tmp_wiki):
    """After invalidation a new page must be findable — corpus must be rebuilt."""
    store = WikiStorage(tmp_wiki / "wiki")
    _write_page(store, "chlorine", "chlorine treats algae")
    _write_page(store, "unrelated", "the quick brown fox jumps over the lazy dog")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    search.bm25_search(["chlorine"], top_n=5)
    assert search._cached_corpus is not None

    search.invalidate_index()
    assert search._cached_corpus is None

    # Third page ensures nitrogen has positive BM25 IDF (N=3, df=1)
    _write_page(store, "nitrogen", "nitrogen fertiliser for lawns")
    results = search.bm25_search(["nitrogen"], top_n=5)
    assert search._cached_corpus is not None
    assert "nitrogen" in [r.slug for r in results]


# ── VectorStore tests ─────────────────────────────────────────────────────────

import pytest

@pytest.mark.asyncio
async def test_vector_store_upsert_and_get(tmp_wiki):
    from synthadoc.storage.search import VectorStore
    store = VectorStore(tmp_wiki / ".synthadoc" / "embeddings.db")
    await store.init()
    emb = [0.1, 0.2, 0.3, 0.4]
    await store.upsert("my-page", emb)
    result = await store.get("my-page")
    assert result is not None
    assert len(result) == 4
    assert abs(result[0] - 0.1) < 1e-5

@pytest.mark.asyncio
async def test_vector_store_get_missing_returns_none(tmp_wiki):
    from synthadoc.storage.search import VectorStore
    store = VectorStore(tmp_wiki / ".synthadoc" / "embeddings.db")
    await store.init()
    assert await store.get("nonexistent") is None

@pytest.mark.asyncio
async def test_vector_store_list_slugs(tmp_wiki):
    from synthadoc.storage.search import VectorStore
    store = VectorStore(tmp_wiki / ".synthadoc" / "embeddings.db")
    await store.init()
    await store.upsert("page-a", [0.1, 0.2])
    await store.upsert("page-b", [0.3, 0.4])
    slugs = await store.list_slugs()
    assert set(slugs) == {"page-a", "page-b"}

@pytest.mark.asyncio
async def test_vector_store_upsert_overwrites(tmp_wiki):
    from synthadoc.storage.search import VectorStore
    store = VectorStore(tmp_wiki / ".synthadoc" / "embeddings.db")
    await store.init()
    await store.upsert("page-a", [0.1, 0.2])
    await store.upsert("page-a", [0.9, 0.8])
    result = await store.get("page-a")
    assert abs(result[0] - 0.9) < 1e-5

@pytest.mark.asyncio
async def test_vector_store_get_all(tmp_wiki):
    from synthadoc.storage.search import VectorStore
    store = VectorStore(tmp_wiki / ".synthadoc" / "embeddings.db")
    await store.init()
    await store.upsert("a", [1.0, 0.0])
    await store.upsert("b", [0.0, 1.0])
    all_embs = await store.get_all()
    assert set(all_embs.keys()) == {"a", "b"}
    assert len(all_embs["a"]) == 2

@pytest.mark.asyncio
async def test_vector_store_count(tmp_wiki):
    from synthadoc.storage.search import VectorStore
    store = VectorStore(tmp_wiki / ".synthadoc" / "embeddings.db")
    await store.init()
    assert await store.count() == 0
    await store.upsert("x", [0.5, 0.5])
    assert await store.count() == 1
    await store.upsert("y", [0.1, 0.9])
    assert await store.count() == 2

@pytest.mark.asyncio
async def test_vector_store_get_all_empty(tmp_wiki):
    from synthadoc.storage.search import VectorStore
    store = VectorStore(tmp_wiki / ".synthadoc" / "embeddings.db")
    await store.init()
    result = await store.get_all()
    assert result == {}

@pytest.mark.asyncio
async def test_vector_store_list_slugs_empty(tmp_wiki):
    from synthadoc.storage.search import VectorStore
    store = VectorStore(tmp_wiki / ".synthadoc" / "embeddings.db")
    await store.init()
    assert await store.list_slugs() == []

@pytest.mark.asyncio
async def test_vector_store_init_idempotent(tmp_wiki):
    from synthadoc.storage.search import VectorStore
    store = VectorStore(tmp_wiki / ".synthadoc" / "embeddings.db")
    await store.init()
    await store.init()  # second call must not crash
    assert await store.count() == 0


# ── HybridSearch vector support tests ────────────────────────────────────────

from unittest.mock import MagicMock, patch

@pytest.mark.asyncio
async def test_hybrid_search_bm25_only_when_vector_disabled(tmp_wiki):
    from synthadoc.storage.search import HybridSearch
    from synthadoc.config import SearchConfig
    store = WikiStorage(tmp_wiki / "wiki")
    _write_page(store, "transformers", "transformers use self-attention mechanisms")
    _write_page(store, "cnn", "CNNs use convolutional filters")
    _write_page(store, "rlhf", "RLHF trains models with human feedback")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db",
                          search_cfg=SearchConfig(vector=False))
    results = await search.hybrid_search(["attention", "transformer"])
    assert any(r.slug == "transformers" for r in results)

@pytest.mark.asyncio
async def test_hybrid_search_returns_empty_for_empty_wiki(tmp_wiki):
    from synthadoc.storage.search import HybridSearch
    from synthadoc.config import SearchConfig
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db",
                          search_cfg=SearchConfig(vector=False))
    results = await search.hybrid_search(["anything"])
    assert results == []

@pytest.mark.asyncio
async def test_hybrid_search_reranks_with_vector(tmp_wiki):
    from synthadoc.storage.search import HybridSearch, VectorStore
    from synthadoc.config import SearchConfig
    store = WikiStorage(tmp_wiki / "wiki")
    _write_page(store, "transformers", "transformers use self-attention mechanisms")
    _write_page(store, "cnn", "CNNs use convolutional filters for image recognition")
    _write_page(store, "rlhf", "RLHF trains models with human feedback rewards")

    cfg = SearchConfig(vector=True, vector_top_candidates=10)
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db", search_cfg=cfg)
    with patch.dict("sys.modules", {"fastembed": MagicMock()}):
        await search.init_vector()

    vs = VectorStore(tmp_wiki / ".synthadoc" / "embeddings.db")
    await vs.upsert("transformers", [1.0, 0.0, 0.0, 0.0])
    await vs.upsert("cnn",          [0.0, 1.0, 0.0, 0.0])
    await vs.upsert("rlhf",         [0.0, 0.0, 1.0, 0.0])

    # query embedding strongly points to "transformers"
    with patch.object(search, "_embed_text", return_value=[1.0, 0.0, 0.0, 0.0]):
        results = await search.hybrid_search(["attention", "transformer"], top_n=3)

    assert results[0].slug == "transformers"

@pytest.mark.asyncio
async def test_hybrid_search_falls_back_to_bm25_when_no_embeddings(tmp_wiki):
    """Vector enabled but embeddings.db is empty — should fall back to BM25 order."""
    from synthadoc.storage.search import HybridSearch
    from synthadoc.config import SearchConfig
    store = WikiStorage(tmp_wiki / "wiki")
    _write_page(store, "transformers", "transformers use self-attention mechanisms")
    _write_page(store, "cnn", "CNNs use convolutional filters")
    _write_page(store, "rlhf", "RLHF trains models with human feedback")

    cfg = SearchConfig(vector=True, vector_top_candidates=10)
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db", search_cfg=cfg)
    with patch.dict("sys.modules", {"fastembed": MagicMock()}):
        await search.init_vector()
    # embeddings.db is empty — hybrid_search must fall back to BM25 without calling _embed_text
    results = await search.hybrid_search(["attention", "transformer"], top_n=3)
    assert any(r.slug == "transformers" for r in results)

@pytest.mark.asyncio
async def test_embed_page_stores_embedding(tmp_wiki):
    from synthadoc.storage.search import HybridSearch, VectorStore
    from synthadoc.config import SearchConfig
    store = WikiStorage(tmp_wiki / "wiki")
    cfg = SearchConfig(vector=True)
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db", search_cfg=cfg)
    with patch.dict("sys.modules", {"fastembed": MagicMock()}):
        await search.init_vector()

    with patch.object(search, "_embed_text", return_value=[0.5, 0.5, 0.0, 0.0]):
        await search.embed_page("my-page", "some text content")

    vs = VectorStore(tmp_wiki / ".synthadoc" / "embeddings.db")
    emb = await vs.get("my-page")
    assert emb is not None
    assert abs(emb[0] - 0.5) < 1e-5

@pytest.mark.asyncio
async def test_embed_page_noop_when_vector_disabled(tmp_wiki):
    from synthadoc.storage.search import HybridSearch, VectorStore
    from synthadoc.config import SearchConfig
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db",
                          search_cfg=SearchConfig(vector=False))
    await search.embed_page("my-page", "some text")
    # embeddings.db should not be created / no entry stored
    if (tmp_wiki / ".synthadoc" / "embeddings.db").exists():
        vs = VectorStore(tmp_wiki / ".synthadoc" / "embeddings.db")
        await vs.init()
        assert await vs.get("my-page") is None

@pytest.mark.asyncio
async def test_embed_page_noop_when_vector_store_not_initialised(tmp_wiki):
    """embed_page before init_vector called must be a safe no-op."""
    from synthadoc.storage.search import HybridSearch
    from synthadoc.config import SearchConfig
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db",
                          search_cfg=SearchConfig(vector=True))
    # init_vector NOT called — _vector_store is None
    await search.embed_page("my-page", "some text")  # must not raise

def test_vector_enabled_false_by_default(tmp_wiki):
    from synthadoc.storage.search import HybridSearch
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    assert search._vector_enabled() is False

def test_vector_enabled_true_when_configured(tmp_wiki):
    from synthadoc.storage.search import HybridSearch
    from synthadoc.config import SearchConfig
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db",
                          search_cfg=SearchConfig(vector=True))
    assert search._vector_enabled() is True

def test_get_embed_model_raises_on_missing_fastembed(tmp_wiki):
    """When fastembed is not installed, _get_embed_model must raise ImportError."""
    import sys
    from synthadoc.storage.search import HybridSearch
    from synthadoc.config import SearchConfig
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db",
                          search_cfg=SearchConfig(vector=True))
    # Temporarily hide fastembed from the import system
    orig = sys.modules.get("fastembed")
    sys.modules["fastembed"] = None  # type: ignore
    try:
        with pytest.raises((ImportError, TypeError)):
            search._get_embed_model()
    finally:
        if orig is None:
            sys.modules.pop("fastembed", None)
        else:
            sys.modules["fastembed"] = orig


@pytest.mark.asyncio
async def test_hybrid_search_partial_embeddings(tmp_wiki):
    """Candidates missing embeddings get score 0.0 — not an error — and rank below those with embeddings."""
    from synthadoc.storage.search import HybridSearch, VectorStore
    from synthadoc.config import SearchConfig

    store = WikiStorage(tmp_wiki / "wiki")
    # Both pages are relevant to the query so they both appear as BM25 candidates
    _write_page(store, "with-emb", "transformers attention mechanisms deep learning neural")
    _write_page(store, "no-emb",   "transformer attention networks vision model")
    _write_page(store, "extra",    "something completely unrelated content here about cooking")

    cfg = SearchConfig(vector=True, vector_top_candidates=10)
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db", search_cfg=cfg)
    with patch.dict("sys.modules", {"fastembed": MagicMock()}):
        await search.init_vector()

    vs = VectorStore(tmp_wiki / ".synthadoc" / "embeddings.db")
    await vs.upsert("with-emb", [1.0, 0.0, 0.0, 0.0])
    # "no-emb" intentionally has no embedding stored

    with patch.object(search, "_embed_text", return_value=[1.0, 0.0, 0.0, 0.0]):
        results = await search.hybrid_search(["attention", "transformer"], top_n=3)

    slugs = [r.slug for r in results]
    assert "with-emb" in slugs, "page with embedding must appear in results"
    assert "no-emb" in slugs, "page without embedding must not be dropped — fallback score 0.0"
    assert slugs.index("with-emb") < slugs.index("no-emb"), \
        "page with matching embedding must rank above page with fallback score 0.0"


# ── vector path gaps ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_init_vector_returns_early_when_vector_disabled(tmp_wiki):
    """init_vector() is a no-op when vector search is not enabled."""
    from synthadoc.storage.search import HybridSearch
    from synthadoc.config import SearchConfig
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db",
                          search_cfg=SearchConfig(vector=False))
    await search.init_vector()  # must not raise and must not create a VectorStore
    assert search._vector_store is None


@pytest.mark.asyncio
async def test_init_vector_raises_when_fastembed_not_installed(tmp_wiki):
    """init_vector() raises ImportError when fastembed is not available."""
    from unittest.mock import patch
    from synthadoc.storage.search import HybridSearch
    from synthadoc.config import SearchConfig
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db",
                          search_cfg=SearchConfig(vector=True))
    with patch.dict("sys.modules", {"fastembed": None}):
        with pytest.raises(ImportError, match="fastembed"):
            await search.init_vector()


def test_get_embed_model_creates_and_caches_model(tmp_wiki):
    """_get_embed_model() constructs the TextEmbedding model once and caches it."""
    from unittest.mock import MagicMock, patch
    from synthadoc.storage.search import HybridSearch
    from synthadoc.config import SearchConfig
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db",
                          search_cfg=SearchConfig(vector=True))
    mock_model = MagicMock()
    mock_te_cls = MagicMock(return_value=mock_model)
    with patch.dict("sys.modules", {"fastembed": MagicMock(TextEmbedding=mock_te_cls)}):
        model_first = search._get_embed_model()
        model_second = search._get_embed_model()
    assert model_first is mock_model
    assert model_second is mock_model
    mock_te_cls.assert_called_once()  # constructed only once


def test_embed_text_returns_float_list(tmp_wiki):
    """_embed_text() calls model.embed and returns a flat list of floats."""
    from unittest.mock import MagicMock, patch
    import numpy as np
    from synthadoc.storage.search import HybridSearch
    from synthadoc.config import SearchConfig
    store = WikiStorage(tmp_wiki / "wiki")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db",
                          search_cfg=SearchConfig(vector=True))
    fake_embedding = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    mock_model = MagicMock()
    mock_model.embed.return_value = [fake_embedding]
    with patch.object(search, "_get_embed_model", return_value=mock_model):
        result = search._embed_text("test text")
    assert isinstance(result, list)
    assert len(result) == 3
    assert abs(result[0] - 0.1) < 1e-5


# ── routing-scoped search ─────────────────────────────────────────────────────

def test_bm25_scoped_slugs_limits_results(tmp_wiki):
    """bm25_search with scoped_slugs must only return results from the given slugs."""
    store = WikiStorage(tmp_wiki / "wiki")
    _write_page(store, "alan-turing", "Alan Turing developed the theoretical basis of computation.")
    _write_page(store, "grace-hopper", "Grace Hopper pioneered compiler development.")
    _write_page(store, "eniac", "ENIAC was the first general-purpose electronic computer.")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")

    results = search.bm25_search(["computer computation"], top_n=5,
                                  scoped_slugs=["alan-turing", "grace-hopper"])
    slugs = [r.slug for r in results]
    assert "eniac" not in slugs
    assert all(s in ("alan-turing", "grace-hopper") for s in slugs)


def test_bm25_scoped_slugs_empty_scope_returns_empty(tmp_wiki):
    """bm25_search with scoped_slugs=[] must return an empty list."""
    store = WikiStorage(tmp_wiki / "wiki")
    _write_page(store, "alan-turing", "Alan Turing developed theoretical computation.")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    results = search.bm25_search(["computation"], top_n=5, scoped_slugs=[])
    assert results == []


def test_bm25_scoped_slugs_none_searches_full_corpus(tmp_wiki):
    """bm25_search with scoped_slugs=None must search the full corpus."""
    store = WikiStorage(tmp_wiki / "wiki")
    _write_page(store, "alan-turing", "Alan Turing developed theoretical computation.")
    _write_page(store, "eniac", "ENIAC was the first electronic computer.")
    _write_page(store, "unrelated", "Cooking is a great hobby for relaxation.")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")
    results = search.bm25_search(["computation computer"], top_n=5, scoped_slugs=None)
    slugs = [r.slug for r in results]
    assert "alan-turing" in slugs or "eniac" in slugs


@pytest.mark.asyncio
async def test_hybrid_search_scoped_slugs_limits_results(tmp_wiki):
    """hybrid_search with scoped_slugs must restrict candidates to the given slugs."""
    store = WikiStorage(tmp_wiki / "wiki")
    _write_page(store, "alan-turing", "Alan Turing developed the theoretical basis of computation.")
    _write_page(store, "grace-hopper", "Grace Hopper pioneered compiler development.")
    _write_page(store, "eniac", "ENIAC was the first general-purpose electronic computer.")
    search = HybridSearch(store, tmp_wiki / ".synthadoc" / "embeddings.db")

    results = await search.hybrid_search(
        ["computer computation"], top_n=5,
        scoped_slugs=["alan-turing", "grace-hopper"]
    )
    slugs = [r.slug for r in results]
    assert "eniac" not in slugs
