# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import threading
import pytest
from synthadoc.storage.wiki import WikiStorage, WikiPage


def test_write_and_read_page(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    page = WikiPage(title="Test", tags=["ai"], content="Hello [[Other]].",
                    status="active", confidence="medium", sources=[])
    store.write_page("test", page)
    loaded = store.read_page("test")
    assert loaded.title == "Test"
    assert "ai" in loaded.tags
    assert "[[Other]]" in loaded.content


def test_frontmatter_in_file(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("x", WikiPage(title="X", tags=["t1"], content="body",
                     status="active", confidence="high", sources=[]))
    raw = (tmp_wiki / "wiki" / "x.md").read_text()
    assert "title: X" in raw
    assert "status: active" in raw


def test_list_pages(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    for name in ("alpha", "beta", "gamma"):
        store.write_page(name, WikiPage(title=name, tags=[], content="",
                         status="active", confidence="medium", sources=[]))
    assert set(store.list_pages()) == {"alpha", "beta", "gamma"}


def test_page_not_found_returns_none(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    assert store.read_page("nonexistent") is None


def test_write_lock_serialises_writes(tmp_wiki):
    store = WikiStorage(tmp_wiki / "wiki")
    results = []
    def write(n):
        with store.page_lock("shared"):
            results.append(n)
    threads = [threading.Thread(target=write, args=(i,)) for i in range(5)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert sorted(results) == [0, 1, 2, 3, 4]


# ── Corner cases ────────────────────────────────────────────────────────────

def test_unicode_title_and_content(tmp_wiki):
    """Pages with CJK titles and emoji in content must round-trip cleanly."""
    store = WikiStorage(tmp_wiki / "wiki")
    page = WikiPage(title="游泳池维护 🏊", tags=["pool", "中文"], content="氯气含量 ppm\n🔬 测试",
                    status="active", confidence="high", sources=[])
    store.write_page("pool-zh", page)
    loaded = store.read_page("pool-zh")
    assert loaded.title == "游泳池维护 🏊"
    assert "氯气含量 ppm" in loaded.content
    assert "中文" in loaded.tags


def test_overwrite_page_replaces_content(tmp_wiki):
    """Writing a page twice must replace the content, not append."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("doc", WikiPage(title="v1", tags=[], content="first",
                     status="active", confidence="medium", sources=[]))
    store.write_page("doc", WikiPage(title="v2", tags=[], content="second",
                     status="active", confidence="high", sources=[]))
    loaded = store.read_page("doc")
    assert loaded.title == "v2"
    assert loaded.content == "second"
    assert "first" not in loaded.content


def test_empty_content_roundtrip(tmp_wiki):
    """A page with empty string content must not raise and must read back empty."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("empty", WikiPage(title="Empty", tags=[], content="",
                     status="active", confidence="low", sources=[]))
    loaded = store.read_page("empty")
    assert loaded.content == ""


def test_categories_roundtrip(tmp_wiki):
    """categories list must be preserved in frontmatter and read back correctly."""
    store = WikiStorage(tmp_wiki / "wiki")
    page = WikiPage(title="Cat Page", tags=[], content="body",
                    status="active", confidence="high", sources=[],
                    categories=["Swimming Pool", "Recently Added"])
    store.write_page("cat-page", page)
    loaded = store.read_page("cat-page")
    assert loaded.categories == ["Swimming Pool", "Recently Added"]


def test_categories_missing_defaults_to_empty(tmp_wiki):
    """Pages written without categories field must read back as empty list."""
    store = WikiStorage(tmp_wiki / "wiki")
    # Write raw markdown without categories in frontmatter
    (tmp_wiki / "wiki").mkdir(parents=True, exist_ok=True)
    (tmp_wiki / "wiki" / "no-cats.md").write_text(
        "---\ntitle: No Cats\ntags: []\nstatus: active\nconfidence: high\nsources: []\n---\n\nbody",
        encoding="utf-8"
    )
    loaded = store.read_page("no-cats")
    assert loaded.categories == []


def test_path_traversal_rejected(tmp_wiki):
    """Slugs containing path traversal sequences must raise PermissionError."""
    store = WikiStorage(tmp_wiki / "wiki")
    with pytest.raises(PermissionError):
        store.read_page("../outside")


def test_orphan_flag_roundtrip(tmp_wiki):
    """orphan=True must be written to and read from frontmatter correctly."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("orphan-page", WikiPage(title="Orphan", tags=[], content="alone",
                     status="active", confidence="low", sources=[], orphan=True))
    loaded = store.read_page("orphan-page")
    assert loaded.orphan is True


def test_set_page_categories_replaces_existing(tmp_wiki):
    """set_page_categories must replace, not append to, existing categories."""
    store = WikiStorage(tmp_wiki / "wiki")
    store.write_page("p", WikiPage(title="P", tags=[], content="x",
                     status="active", confidence="medium", sources=[],
                     categories=["Old Category"]))
    store.set_page_categories("p", ["New Category"])
    loaded = store.read_page("p")
    assert loaded.categories == ["New Category"]
    assert "Old Category" not in loaded.categories


def test_append_to_index_no_duplicate(tmp_wiki):
    """append_to_index must not add a slug that is already linked in index.md."""
    store = WikiStorage(tmp_wiki / "wiki")
    index_path = tmp_wiki / "wiki" / "index.md"
    index_path.write_text("---\ntitle: Index\n---\n\n- [[my-page]]\n", encoding="utf-8")
    store.write_page("my-page", WikiPage(title="My Page", tags=[], content="",
                     status="active", confidence="medium", sources=[]))
    store.append_to_index("my-page", "My Page")
    content = index_path.read_text(encoding="utf-8")
    assert content.count("[[my-page]]") == 1


def test_append_to_index_creates_recently_added(tmp_wiki):
    """append_to_index must create ## Recently Added section if absent."""
    store = WikiStorage(tmp_wiki / "wiki")
    index_path = tmp_wiki / "wiki" / "index.md"
    index_path.write_text("---\ntitle: Index\n---\n\n## Some Category\n", encoding="utf-8")
    store.write_page("new-page", WikiPage(title="New Page", tags=[], content="",
                     status="active", confidence="medium", sources=[]))
    store.append_to_index("new-page", "New Page")
    content = index_path.read_text(encoding="utf-8")
    assert "## Recently Added" in content
    assert "[[new-page]]" in content


def test_concurrent_writes_to_different_pages(tmp_wiki):
    """Concurrent writes to different slugs must not interfere with each other."""
    store = WikiStorage(tmp_wiki / "wiki")
    errors = []

    def write_page(slug):
        try:
            store.write_page(slug, WikiPage(title=slug, tags=[], content=f"content-{slug}",
                             status="active", confidence="medium", sources=[]))
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=write_page, args=(f"page-{i}",)) for i in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert errors == []
    assert len(store.list_pages()) == 10
