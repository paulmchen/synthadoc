# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import pytest
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
