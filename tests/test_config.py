# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest
from pathlib import Path
from synthadoc.config import Config, AgentConfig, load_config


def test_load_minimal_config(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('[agents]\ndefault = { provider = "anthropic", model = "claude-opus-4-6" }\n')
    cfg = load_config(project_config=cfg_file)
    assert cfg.agents.default.provider == "anthropic"
    assert cfg.agents.default.model == "claude-opus-4-6"


def test_agent_override_inherits_default(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        '[agents]\ndefault = { provider = "anthropic", model = "claude-opus-4-6" }\n'
        'lint = { model = "claude-haiku-4-5" }\n'
    )
    cfg = load_config(project_config=cfg_file)
    lint = cfg.agents.resolve("lint")
    assert lint.provider == "anthropic"
    assert lint.model == "claude-haiku-4-5"


def test_cost_defaults():
    cfg = load_config()
    assert cfg.cost.soft_warn_usd == 0.50
    assert cfg.cost.hard_gate_usd == 2.00
    assert cfg.cost.auto_resolve_confidence_threshold == 0.85


def test_ingest_defaults():
    cfg = load_config()
    assert cfg.ingest.max_pages_per_ingest == 15


def test_queue_defaults():
    cfg = load_config()
    assert cfg.queue.max_parallel_ingest == 4
    assert cfg.queue.max_retries == 3
    assert cfg.queue.backoff_base_seconds == 5


def test_unlimited_wikis(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        '[wikis]\nresearch = "~/wikis/research"\nwork = "~/wikis/work"\n'
        'life = "~/wikis/life"\nhobby = "~/wikis/hobby"\nhealth = "~/wikis/health"\n'
    )
    cfg = load_config(project_config=cfg_file)
    assert len(cfg.wikis) == 5
    assert "life" in cfg.wikis
    assert "hobby" in cfg.wikis


def test_project_config_overrides_global(tmp_path):
    global_cfg = tmp_path / "global.toml"
    project_cfg = tmp_path / "project.toml"
    global_cfg.write_text('[agents]\ndefault = { provider = "anthropic", model = "claude-opus-4-6" }\n')
    project_cfg.write_text('[agents]\ndefault = { provider = "openai", model = "gpt-4o" }\n')
    cfg = load_config(global_config=global_cfg, project_config=project_cfg)
    assert cfg.agents.default.provider == "openai"
    assert cfg.agents.default.model == "gpt-4o"


def test_missing_agents_default_raises(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('[cost]\nsoft_warn_usd = 0.10\n')
    with pytest.raises(ValueError, match="agents.default"):
        load_config(global_config=cfg_file)


def test_invalid_provider_name_raises(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('[agents]\ndefault = { provider = "notareal", model = "x" }\n')
    with pytest.raises(ValueError, match="Unknown provider"):
        load_config(global_config=cfg_file)


def test_query_config_defaults():
    """Config must expose query.gap_score_threshold with default 2.0."""
    cfg = load_config()
    assert hasattr(cfg, "query")
    assert cfg.query.gap_score_threshold == 2.0


def test_query_config_can_be_set_from_toml():
    import tempfile, os
    from pathlib import Path
    toml = b'[agents.default]\nprovider = "anthropic"\nmodel = "claude-haiku-4-5-20251001"\n[query]\ngap_score_threshold = 1.5\n'
    with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
        f.write(toml)
        path = Path(f.name)
    try:
        cfg = load_config(project_config=path)
        assert cfg.query.gap_score_threshold == 1.5
    finally:
        os.unlink(path)
