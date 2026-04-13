# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest
from pathlib import Path
from synthadoc.cli._init import init_wiki


def test_init_wiki_writes_custom_port(tmp_path):
    """config.toml must contain the port passed to init_wiki."""
    init_wiki(tmp_path, domain="Robotics", port=7071)
    config = (tmp_path / ".synthadoc" / "config.toml").read_text()
    assert "port = 7071" in config
    assert "port = 7070" not in config


def test_init_wiki_default_port_is_7070(tmp_path):
    """Default port when not specified must be 7070."""
    init_wiki(tmp_path, domain="General")
    config = (tmp_path / ".synthadoc" / "config.toml").read_text()
    assert "port = 7070" in config


def test_init_wiki_writes_domain_to_config(tmp_path):
    """config.toml must persist the domain under [wiki] domain."""
    init_wiki(tmp_path, domain="Machine Learning", port=7070)
    config = (tmp_path / ".synthadoc" / "config.toml").read_text()
    assert 'domain = "Machine Learning"' in config


def test_init_wiki_creates_expected_files(tmp_path):
    """All scaffold files must be created."""
    init_wiki(tmp_path, domain="General")
    assert (tmp_path / "wiki" / "index.md").exists()
    assert (tmp_path / "wiki" / "purpose.md").exists()
    assert (tmp_path / "wiki" / "dashboard.md").exists()
    assert (tmp_path / "AGENTS.md").exists()
    assert (tmp_path / ".synthadoc" / "config.toml").exists()
