# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
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
