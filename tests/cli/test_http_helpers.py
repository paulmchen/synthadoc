# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import httpx
import pytest
from unittest.mock import MagicMock, patch

import typer


def _make_status_error(status: int, method: str, url: str) -> httpx.HTTPStatusError:
    req = httpx.Request(method, url)
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.json.return_value = {"detail": f"HTTP {status}"}
    resp.text = f"HTTP {status}"
    return httpx.HTTPStatusError(str(status), request=req, response=resp)


# ── _detail() ────────────────────────────────────────────────────────────────

def test_detail_extracts_json_detail():
    from synthadoc.cli._http import _detail
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = {"detail": "Page not found"}
    assert _detail(resp) == "Page not found"


def test_detail_falls_back_to_text():
    from synthadoc.cli._http import _detail
    resp = MagicMock(spec=httpx.Response)
    resp.json.side_effect = ValueError("not JSON")
    resp.text = "  internal server error  "
    assert _detail(resp) == "internal server error"


# ── _timeout_error() ─────────────────────────────────────────────────────────

def test_timeout_error_query_path_exits():
    from synthadoc.cli._http import _timeout_error
    with pytest.raises(typer.Exit):
        _timeout_error("/query", 60)


def test_timeout_error_jobs_path_exits():
    from synthadoc.cli._http import _timeout_error
    with pytest.raises(typer.Exit):
        _timeout_error("/jobs/123", 10)


def test_timeout_error_other_path_exits():
    from synthadoc.cli._http import _timeout_error
    with pytest.raises(typer.Exit):
        _timeout_error("/status", 30)


# ── get() ────────────────────────────────────────────────────────────────────

def test_get_connect_error_exits():
    from synthadoc.cli._http import get
    with patch("synthadoc.cli._http.server_url", return_value="http://127.0.0.1:7070"), \
         patch.object(httpx, "get", side_effect=httpx.ConnectError("refused")):
        with pytest.raises(typer.Exit):
            get("my-wiki", "/status")


def test_get_read_timeout_exits():
    from synthadoc.cli._http import get
    with patch("synthadoc.cli._http.server_url", return_value="http://127.0.0.1:7070"), \
         patch.object(httpx, "get", side_effect=httpx.ReadTimeout("timeout")):
        with pytest.raises(typer.Exit):
            get("my-wiki", "/query")


def test_get_http_status_error_exits():
    from synthadoc.cli._http import get
    err = _make_status_error(500, "GET", "http://127.0.0.1:7070/status")
    with patch("synthadoc.cli._http.server_url", return_value="http://127.0.0.1:7070"), \
         patch.object(httpx, "get", side_effect=err):
        with pytest.raises(typer.Exit):
            get("my-wiki", "/status")


# ── post() ───────────────────────────────────────────────────────────────────

def test_post_connect_error_exits():
    from synthadoc.cli._http import post
    with patch("synthadoc.cli._http.server_url", return_value="http://127.0.0.1:7070"), \
         patch.object(httpx, "post", side_effect=httpx.ConnectError("refused")):
        with pytest.raises(typer.Exit):
            post("my-wiki", "/ingest", {})


def test_post_read_timeout_exits():
    from synthadoc.cli._http import post
    with patch("synthadoc.cli._http.server_url", return_value="http://127.0.0.1:7070"), \
         patch.object(httpx, "post", side_effect=httpx.ReadTimeout("timeout")):
        with pytest.raises(typer.Exit):
            post("my-wiki", "/jobs/cancel", {})


def test_post_http_status_error_exits():
    from synthadoc.cli._http import post
    err = _make_status_error(422, "POST", "http://127.0.0.1:7070/ingest")
    with patch("synthadoc.cli._http.server_url", return_value="http://127.0.0.1:7070"), \
         patch.object(httpx, "post", side_effect=err):
        with pytest.raises(typer.Exit):
            post("my-wiki", "/ingest", {"source": "x"})


# ── delete() ─────────────────────────────────────────────────────────────────

def test_delete_connect_error_exits():
    from synthadoc.cli._http import delete
    with patch("synthadoc.cli._http.server_url", return_value="http://127.0.0.1:7070"), \
         patch.object(httpx, "delete", side_effect=httpx.ConnectError("refused")):
        with pytest.raises(typer.Exit):
            delete("my-wiki", "/jobs/abc")


def test_delete_http_status_error_exits():
    from synthadoc.cli._http import delete
    err = _make_status_error(404, "DELETE", "http://127.0.0.1:7070/jobs/abc")
    with patch("synthadoc.cli._http.server_url", return_value="http://127.0.0.1:7070"), \
         patch.object(httpx, "delete", side_effect=err):
        with pytest.raises(typer.Exit):
            delete("my-wiki", "/jobs/abc")
