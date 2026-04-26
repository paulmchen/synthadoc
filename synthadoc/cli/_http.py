# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from __future__ import annotations

"""Shared HTTP client helpers for CLI thin-client commands."""

import httpx
import typer

from synthadoc.config import load_config
from synthadoc.cli.install import resolve_wiki_path
from synthadoc import errors as E


def server_url(wiki: str) -> str:
    """Return the base URL for the wiki's server."""
    root = resolve_wiki_path(wiki)
    config_path = root / ".synthadoc" / "config.toml"
    if not config_path.exists():
        E.cli_error(
            E.WIKI_NOT_REGISTERED,
            f"Wiki '{wiki}' is not installed.",
            f"Make sure wiki '{wiki}' was installed with 'synthadoc install'.",
        )
    cfg = load_config(project_config=config_path)
    port = cfg.server.port
    return f"http://127.0.0.1:{port}"


def get(wiki: str, path: str, timeout: int = 60, **params) -> dict:
    url = server_url(wiki)
    try:
        resp = httpx.get(f"{url}{path}", params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        _no_server(wiki)
    except httpx.ReadTimeout:
        _timeout_error(path, timeout)
    except httpx.HTTPStatusError as e:
        E.cli_error(E.SRV_HTTP_ERROR,
                    f"Server returned {e.response.status_code}: {_detail(e.response)}")


def post(wiki: str, path: str, body: dict, timeout: int = 60) -> dict:
    url = server_url(wiki)
    try:
        resp = httpx.post(f"{url}{path}", json=body, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        _no_server(wiki)
    except httpx.ReadTimeout:
        _timeout_error(path, timeout)
    except httpx.HTTPStatusError as e:
        E.cli_error(E.SRV_HTTP_ERROR,
                    f"Server returned {e.response.status_code}: {_detail(e.response)}")


def delete(wiki: str, path: str) -> dict:
    url = server_url(wiki)
    try:
        resp = httpx.delete(f"{url}{path}", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        _no_server(wiki)
    except httpx.HTTPStatusError as e:
        E.cli_error(E.SRV_HTTP_ERROR,
                    f"Server returned {e.response.status_code}: {_detail(e.response)}")


def _timeout_error(path: str, timeout: int) -> None:
    if "/query" in path:
        E.cli_error(
            E.QUERY_TIMEOUT,
            f"The query timed out waiting for the LLM to respond ({timeout} s).",
            "The wiki server is still running. Try again — if the wiki is large, "
            "reduce your question scope or pass --timeout 120 to allow more time.",
        )
    elif "/jobs" in path:
        E.cli_error(
            E.QUERY_TIMEOUT,
            f"The server did not respond to '{path}' within {timeout} s.",
            "The server may be busy processing a large file (e.g. a PDF). "
            "Wait a moment and try again.",
        )
    else:
        E.cli_error(
            E.QUERY_TIMEOUT,
            f"The request timed out waiting for the server to respond ({timeout} s).",
            "The wiki server is still running. Try again.",
        )


def _detail(response: httpx.Response) -> str:
    """Extract FastAPI's detail string from a JSON error response, or return raw text."""
    try:
        return response.json()["detail"]
    except Exception:
        return response.text.strip()


def _no_server(wiki: str) -> None:
    E.cli_error(
        E.SRV_NOT_RUNNING,
        f"No synthadoc server is running for wiki '{wiki}'.",
        f"Start it with:\n  synthadoc serve -w {wiki}",
    )
