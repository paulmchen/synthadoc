# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import json, sys, time, pytest
from synthadoc.core.hooks import HookExecutor

_PY = sys.executable


def test_hook_receives_json_context(tmp_path):
    output = tmp_path / "out.json"
    script = tmp_path / "hook.py"
    script.write_text(
        f"import sys,json\ndata=json.load(sys.stdin)\n"
        f"open(r'{output}','w').write(json.dumps(data))\n", encoding="utf-8")
    executor = HookExecutor({"on_ingest_complete": f"{_PY} {script}"})
    executor.fire("on_ingest_complete", {"event": "on_ingest_complete", "wiki": "test"})
    time.sleep(0.5)
    assert output.exists()
    assert json.loads(output.read_text())["wiki"] == "test"


def test_unknown_event_is_noop():
    HookExecutor({}).fire("on_unknown", {"event": "on_unknown"})


def test_blocking_hook_raises_on_failure(tmp_path):
    script = tmp_path / "fail.py"
    script.write_text("import sys; sys.exit(1)\n", encoding="utf-8")
    executor = HookExecutor({"on_ingest_complete": {"cmd": f"{_PY} {script}", "blocking": True}})
    with pytest.raises(RuntimeError, match="Hook failed"):
        executor.fire_blocking("on_ingest_complete", {"event": "on_ingest_complete"})


def test_nonblocking_hook_failure_logs_warning_does_not_raise(tmp_path, caplog):
    """Non-blocking hooks that fail must log a warning but never propagate the exception."""
    import logging, time
    script = tmp_path / "fail_nb.py"
    script.write_text("import sys; sys.exit(1)\n", encoding="utf-8")
    executor = HookExecutor({"on_ingest_complete": f"{_PY} {script}"})
    with caplog.at_level(logging.WARNING):
        executor.fire("on_ingest_complete", {"event": "on_ingest_complete"})
        time.sleep(0.5)
    assert any("hook" in r.message.lower() for r in caplog.records)


def test_on_job_dead_hook_fires(tmp_path):
    """on_dead_job event must reach the hook via fire()."""
    output = tmp_path / "out.json"
    script = tmp_path / "hook.py"
    script.write_text(
        f"import sys, json\ndata=json.load(sys.stdin)\n"
        f"open(r'{output}','w').write(json.dumps(data))\n", encoding="utf-8"
    )
    executor = HookExecutor({"on_dead_job": f"{_PY} {script}"})
    executor.fire("on_dead_job", {"event": "on_dead_job", "job_id": "abc", "wiki": "test"})
    time.sleep(0.5)
    assert output.exists()
    data = json.loads(output.read_text())
    assert data["event"] == "on_dead_job"


def test_hook_config_loaded_from_toml(tmp_path):
    """Hooks declared in config.toml are wired into HookExecutor by the Orchestrator."""
    from synthadoc.config import load_config
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        '[agents]\ndefault = { provider = "anthropic", model = "claude-opus-4-6" }\n'
        '[hooks]\non_ingest_complete = "python hooks/auto_commit.py"\n'
    )
    cfg = load_config(project_config=cfg_file)
    assert "on_ingest_complete" in cfg.hooks
    executor = HookExecutor(cfg.hooks)
    assert executor._hooks.get("on_ingest_complete") == "python hooks/auto_commit.py"
