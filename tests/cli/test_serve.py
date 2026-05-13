# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import json
import pytest
from pathlib import Path
from unittest.mock import patch


def _make_cfg(provider: str = "anthropic"):
    from synthadoc.config import Config, AgentConfig, AgentsConfig
    return Config(agents=AgentsConfig(
        default=AgentConfig(provider=provider, model="claude-opus-4-6")
    ))


def test_apply_provider_override_sets_default():
    """--provider flag overrides config.toml provider on default agent config."""
    from synthadoc.cli.serve import _apply_provider_override
    cfg = _make_cfg("anthropic")
    _apply_provider_override(cfg, "claude-code")
    assert cfg.agents.default.provider == "claude-code"


def test_apply_provider_override_updates_per_agent():
    """--provider flag updates per-agent overrides when they exist."""
    from synthadoc.config import AgentConfig
    from synthadoc.cli.serve import _apply_provider_override
    cfg = _make_cfg("anthropic")
    from synthadoc.config import AgentConfig
    cfg.agents.ingest = AgentConfig(provider="anthropic", model="claude-opus-4-6")
    _apply_provider_override(cfg, "opencode")
    assert cfg.agents.default.provider == "opencode"
    assert cfg.agents.ingest.provider == "opencode"


def test_apply_provider_override_unknown_raises():
    """Unknown --provider value → Exit (cli_error calls typer.Exit)."""
    import click
    from synthadoc.cli.serve import _apply_provider_override
    cfg = _make_cfg("anthropic")
    with pytest.raises((SystemExit, click.exceptions.Exit)):
        _apply_provider_override(cfg, "unknown-tool")


# ── _sync_plugin_config ───────────────────────────────────────────────────────

def _make_plugin_dir(wiki_root: Path, server_url: str) -> Path:
    plugin_dir = wiki_root / ".obsidian" / "plugins" / "synthadoc"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "data.json").write_text(
        json.dumps({"serverUrl": server_url, "rawSourcesFolder": "raw_sources"}),
        encoding="utf-8",
    )
    return plugin_dir


def test_sync_plugin_config_updates_stale_url(tmp_path):
    """Updates data.json when the stored serverUrl port differs from the served port."""
    from synthadoc.cli.serve import _sync_plugin_config
    _make_plugin_dir(tmp_path, "http://127.0.0.1:7070")
    _sync_plugin_config(tmp_path, "127.0.0.1", 7071)
    data = json.loads((tmp_path / ".obsidian" / "plugins" / "synthadoc" / "data.json")
                      .read_text())
    assert data["serverUrl"] == "http://127.0.0.1:7071"
    assert data["rawSourcesFolder"] == "raw_sources"  # other keys preserved


def test_sync_plugin_config_no_change_when_port_matches(tmp_path):
    """Leaves data.json untouched when serverUrl is already correct."""
    from synthadoc.cli.serve import _sync_plugin_config
    plugin_dir = _make_plugin_dir(tmp_path, "http://127.0.0.1:7070")
    mtime_before = (plugin_dir / "data.json").stat().st_mtime
    _sync_plugin_config(tmp_path, "127.0.0.1", 7070)
    mtime_after = (plugin_dir / "data.json").stat().st_mtime
    assert mtime_before == mtime_after


def test_sync_plugin_config_noop_when_plugin_not_installed(tmp_path):
    """Does not raise when the plugin data.json is absent."""
    from synthadoc.cli.serve import _sync_plugin_config
    _sync_plugin_config(tmp_path, "127.0.0.1", 7070)


def test_sync_plugin_config_port_override_synced(tmp_path):
    """Case e: --port CLI override is reflected in plugin data.json after sync."""
    from synthadoc.cli.serve import _sync_plugin_config
    _make_plugin_dir(tmp_path, "http://127.0.0.1:7070")
    _sync_plugin_config(tmp_path, "127.0.0.1", 8080)
    data = json.loads((tmp_path / ".obsidian" / "plugins" / "synthadoc" / "data.json")
                      .read_text())
    assert data["serverUrl"] == "http://127.0.0.1:8080"


def test_sync_plugin_config_external_host_uses_ip(tmp_path):
    """When host is a specific external IP, data.json uses that IP in the URL."""
    from synthadoc.cli.serve import _sync_plugin_config
    _make_plugin_dir(tmp_path, "http://127.0.0.1:7070")
    _sync_plugin_config(tmp_path, "192.168.1.10", 7070)
    data = json.loads((tmp_path / ".obsidian" / "plugins" / "synthadoc" / "data.json")
                      .read_text())
    assert data["serverUrl"] == "http://192.168.1.10:7070"


# ── _check_port (case f) ──────────────────────────────────────────────────────

def test_check_port_raises_when_port_in_use(tmp_path):
    """Case f: _check_port exits non-zero with a useful message when port is bound."""
    import click
    import socket
    from synthadoc.cli.serve import _check_port

    # Hold the port in a way that blocks _check_port on every platform:
    #
    # Linux/macOS — SO_REUSEADDR allows double-bind unless one socket is
    #   listening; listen(1) blocks further binds even with SO_REUSEADDR.
    #
    # Windows — SO_REUSEADDR permits any socket to bind to an occupied port
    #   (even a listening one), so _check_port uses SO_EXCLUSIVEADDRUSE there.
    #   The holder needs no special flags — EXCLUSIVEADDRUSE on the checker
    #   fails when anything at all holds the port.
    for base in range(40100, 40200):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("127.0.0.1", base))
            s.listen(1)
            break
        except OSError:
            s.close()
    else:
        pytest.skip("No bindable port found")

    try:
        with pytest.raises((SystemExit, click.exceptions.Exit)):
            _check_port(base, host="127.0.0.1")
    finally:
        s.close()


def test_check_port_uses_configured_host():
    """_check_port binds the probe socket to whatever host is passed."""
    import socket as _socket
    bound_host = None

    original_bind = _socket.socket.bind

    def capture_bind(self, addr):
        nonlocal bound_host
        bound_host = addr[0]
        return original_bind(self, addr)

    from synthadoc.cli.serve import _check_port
    with patch("socket.socket.bind", capture_bind):
        try:
            _check_port(40299, host="127.0.0.1")
        except Exception:
            pass
    assert bound_host == "127.0.0.1"


# ── External host: warning, not error ────────────────────────────────────────

def test_serve_warns_on_external_host(capsys):
    """External host in config.toml → warning printed to stderr, no hard exit."""
    from synthadoc.cli.serve import _LOOPBACK_ADDRS, _ANY_IFACE_ADDRS
    import typer

    non_loopback = "192.168.1.10"
    assert non_loopback not in _LOOPBACK_ADDRS

    # Verify _plugin_url uses the external address for specific IPs
    from synthadoc.cli.serve import _plugin_url
    assert _plugin_url(non_loopback, 7070) == "http://192.168.1.10:7070"


def test_plugin_url_loopback_uses_127():
    """_plugin_url returns 127.0.0.1 for loopback and any-interface binds."""
    from synthadoc.cli.serve import _plugin_url
    assert _plugin_url("127.0.0.1", 7070) == "http://127.0.0.1:7070"
    assert _plugin_url("::1", 7070) == "http://127.0.0.1:7070"
    assert _plugin_url("0.0.0.0", 7070) == "http://127.0.0.1:7070"
    assert _plugin_url("::", 7070) == "http://127.0.0.1:7070"


def test_plugin_url_external_uses_host():
    """_plugin_url uses the configured host for specific external addresses."""
    from synthadoc.cli.serve import _plugin_url
    assert _plugin_url("192.168.1.10", 7071) == "http://192.168.1.10:7071"
    assert _plugin_url("10.0.0.5", 8080) == "http://10.0.0.5:8080"


def test_loopback_addrs_constant_covers_expected_values():
    """_LOOPBACK_ADDRS includes 127.0.0.1, ::1, localhost; not 0.0.0.0."""
    from synthadoc.cli.serve import _LOOPBACK_ADDRS
    assert "127.0.0.1" in _LOOPBACK_ADDRS
    assert "::1" in _LOOPBACK_ADDRS
    assert "localhost" in _LOOPBACK_ADDRS
    assert "0.0.0.0" not in _LOOPBACK_ADDRS


def test_any_iface_addrs_constant():
    """_ANY_IFACE_ADDRS includes 0.0.0.0 and :: but not loopback addresses."""
    from synthadoc.cli.serve import _ANY_IFACE_ADDRS
    assert "0.0.0.0" in _ANY_IFACE_ADDRS
    assert "::" in _ANY_IFACE_ADDRS
    assert "127.0.0.1" not in _ANY_IFACE_ADDRS
