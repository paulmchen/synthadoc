# Copyright (c) 2026 William Johnason / axoviq.com
import pytest
from fastapi.testclient import TestClient


# ── /routing/status ──────────────────────────────────────────────────────────

def test_routing_status_not_initialized(tmp_wiki):
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        r = client.get("/routing/status")
    assert r.status_code == 200
    data = r.json()
    assert data["exists"] is False
    assert data["branches"] == 0
    assert data["slugs"] == 0
    assert data["content"] == ""


def test_routing_status_initialized(tmp_wiki):
    routing = tmp_wiki / "ROUTING.md"
    routing.write_text("## People\n- [[alan-turing]]\n", encoding="utf-8")
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        r = client.get("/routing/status")
    assert r.status_code == 200
    data = r.json()
    assert data["exists"] is True
    assert data["branches"] == 1
    assert data["slugs"] == 1
    assert "alan-turing" in data["content"]


# ── /routing/init ─────────────────────────────────────────────────────────────

def test_routing_init_creates_routing_md(tmp_wiki):
    index = tmp_wiki / "wiki" / "index.md"
    index.write_text(
        "## People\n- [[alan-turing]]\n- [[grace-hopper]]\n\n"
        "## Hardware\n- [[von-neumann-architecture]]\n",
        encoding="utf-8",
    )
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        r = client.post("/routing/init")
    assert r.status_code == 200
    data = r.json()
    assert data["branches"] == 2
    assert data["slugs"] == 3
    assert "alan-turing" in data["content"]
    assert (tmp_wiki / "ROUTING.md").exists()


def test_routing_init_returns_409_if_already_exists(tmp_wiki):
    (tmp_wiki / "ROUTING.md").write_text("## People\n- [[alan-turing]]\n", encoding="utf-8")
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        r = client.post("/routing/init")
    assert r.status_code == 409
    assert "already exists" in r.json()["detail"]


def test_routing_init_returns_400_if_index_missing(tmp_wiki):
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        r = client.post("/routing/init")
    assert r.status_code == 400
    assert "index.md" in r.json()["detail"]


# ── /routing/validate ─────────────────────────────────────────────────────────

def test_routing_validate_clean(tmp_wiki):
    (tmp_wiki / "ROUTING.md").write_text("## People\n- [[alan-turing]]\n", encoding="utf-8")
    (tmp_wiki / "wiki" / "alan-turing.md").write_text("# Alan Turing\n", encoding="utf-8")
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        r = client.post("/routing/validate")
    assert r.status_code == 200
    data = r.json()
    assert data["clean"] is True
    assert data["dangling"] == []


def test_routing_validate_reports_dangling(tmp_wiki):
    (tmp_wiki / "ROUTING.md").write_text(
        "## People\n- [[alan-turing]]\n- [[john-mccarthy]]\n", encoding="utf-8"
    )
    (tmp_wiki / "wiki" / "alan-turing.md").write_text("# Alan Turing\n", encoding="utf-8")
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        r = client.post("/routing/validate")
    assert r.status_code == 200
    data = r.json()
    assert data["clean"] is False
    assert len(data["dangling"]) == 1
    assert data["dangling"][0] == {"branch": "People", "slug": "john-mccarthy"}


def test_routing_validate_returns_404_if_routing_missing(tmp_wiki):
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        r = client.post("/routing/validate")
    assert r.status_code == 404


# ── /routing/clean ────────────────────────────────────────────────────────────

def test_routing_clean_removes_dangling(tmp_wiki):
    (tmp_wiki / "ROUTING.md").write_text(
        "## People\n- [[alan-turing]]\n- [[john-mccarthy]]\n", encoding="utf-8"
    )
    (tmp_wiki / "wiki" / "alan-turing.md").write_text("# Alan Turing\n", encoding="utf-8")
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        r = client.post("/routing/clean")
    assert r.status_code == 200
    data = r.json()
    assert len(data["removed"]) == 1
    assert data["removed"][0] == {"branch": "People", "slug": "john-mccarthy"}
    assert "john-mccarthy" not in data["content"]
    assert "alan-turing" in data["content"]


def test_routing_clean_nothing_to_remove(tmp_wiki):
    (tmp_wiki / "ROUTING.md").write_text("## People\n- [[alan-turing]]\n", encoding="utf-8")
    (tmp_wiki / "wiki" / "alan-turing.md").write_text("# Alan Turing\n", encoding="utf-8")
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        r = client.post("/routing/clean")
    assert r.status_code == 200
    data = r.json()
    assert data["removed"] == []


def test_routing_clean_returns_404_if_routing_missing(tmp_wiki):
    from synthadoc.integration.http_server import create_app
    with TestClient(create_app(wiki_root=tmp_wiki)) as client:
        r = client.post("/routing/clean")
    assert r.status_code == 404
