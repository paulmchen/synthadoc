# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
from typer.testing import CliRunner
from synthadoc.cli.main import app

runner = CliRunner()


def test_version():
    from synthadoc import __version__
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_no_args_shows_help():
    """Bare `synthadoc` must print usage, not silently exit."""
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "Usage" in result.output
    assert "synthadoc" in result.output.lower()


# ---------------------------------------------------------------------------
# install
# ---------------------------------------------------------------------------

def test_install_creates_fresh_wiki(tmp_path, monkeypatch):
    """install creates wiki structure and registers the path."""
    import synthadoc.cli.install as install_mod
    monkeypatch.setattr(install_mod, "_REGISTRY", tmp_path / "wikis.json")
    monkeypatch.setattr(install_mod, "_find_free_port", lambda start=7070, max_scan=20: 7070)
    # Prevent a real LLM call: _run_scaffold checks for API keys in the environment
    # and will call the provider if one is set (e.g. GEMINI_API_KEY on a dev machine).
    monkeypatch.setattr(install_mod, "_run_scaffold", lambda dest, domain: None)

    result = runner.invoke(app, ["install", "my-wiki", "--target", str(tmp_path)])
    assert result.exit_code == 0, result.output

    dest = tmp_path / "my-wiki"
    assert (dest / "AGENTS.md").exists()
    assert (dest / "log.md").exists()
    assert (dest / "wiki" / "index.md").exists()
    assert (dest / ".synthadoc" / "config.toml").exists()

    registry = install_mod._read_registry()
    assert "my-wiki" in registry
    assert registry["my-wiki"]["path"] == str(dest.resolve())
    assert registry["my-wiki"]["demo"] is None


def test_install_demo_copies_template(tmp_path, monkeypatch):
    """install --demo copies the demo template and flags it in the registry."""
    import synthadoc.cli.install as install_mod
    source = tmp_path / "tpl"
    source.mkdir()
    (source / "wiki").mkdir()
    (source / "wiki" / "index.md").write_text("# Index")
    monkeypatch.setattr(install_mod, "_DEMOS", {"my-demo": source})
    monkeypatch.setattr(install_mod, "_REGISTRY", tmp_path / "wikis.json")
    monkeypatch.setattr(install_mod, "_find_free_port", lambda start=7070, max_scan=20: 7070)

    result = runner.invoke(app, ["install", "my-demo", "--target", str(tmp_path), "--demo"])
    assert result.exit_code == 0, result.output

    dest = tmp_path / "my-demo"
    assert (dest / "wiki" / "index.md").exists()
    registry = install_mod._read_registry()
    assert registry["my-demo"]["demo"] == "my-demo"


def test_install_fails_if_already_registered(tmp_path, monkeypatch):
    """install shows reinstall instructions when wiki is already in the registry."""
    import synthadoc.cli.install as install_mod
    monkeypatch.setattr(install_mod, "_REGISTRY", tmp_path / "wikis.json")
    dest = tmp_path / "my-wiki"
    dest.mkdir()
    install_mod._write_registry({"my-wiki": {"path": str(dest), "demo": None, "installed": "2026-04-09"}})

    result = runner.invoke(app, ["install", "my-wiki", "--target", str(tmp_path)])
    assert result.exit_code != 0
    assert "already installed" in result.output
    assert "uninstall" in result.output


def test_install_fails_if_dest_exists_untracked(tmp_path, monkeypatch):
    """install explains manual removal when directory exists but is not in registry."""
    import synthadoc.cli.install as install_mod
    monkeypatch.setattr(install_mod, "_REGISTRY", tmp_path / "wikis.json")
    (tmp_path / "existing").mkdir()

    result = runner.invoke(app, ["install", "existing", "--target", str(tmp_path)])
    assert result.exit_code != 0
    assert "not tracked" in result.output
    assert "Remove-Item" in result.output or "rm -rf" in result.output


def test_install_unknown_demo_exits_nonzero(tmp_path, monkeypatch):
    """install --demo with an unknown name exits non-zero."""
    import synthadoc.cli.install as install_mod
    monkeypatch.setattr(install_mod, "_DEMOS", {})
    monkeypatch.setattr(install_mod, "_REGISTRY", tmp_path / "wikis.json")

    result = runner.invoke(app, ["install", "no-such-demo", "--target", str(tmp_path), "--demo"])
    assert result.exit_code != 0


def test_install_output_instructs_parent_dir(tmp_path, monkeypatch):
    """install output must confirm installation and show the serve command."""
    import synthadoc.cli.install as install_mod
    monkeypatch.setattr(install_mod, "_REGISTRY", tmp_path / "wikis.json")
    monkeypatch.setattr(install_mod, "_find_free_port", lambda start=7070, max_scan=20: 7070)
    monkeypatch.setattr(install_mod, "_run_scaffold", lambda dest, domain: None)

    result = runner.invoke(app, ["install", "my-research", "--target", str(tmp_path)])
    # No absolute paths in output
    assert str(tmp_path) not in result.output
    # Must confirm installation by name
    assert "my-research" in result.output
    # Must show serve command
    assert "synthadoc serve -w my-research" in result.output


# ---------------------------------------------------------------------------
# uninstall
# ---------------------------------------------------------------------------

def test_uninstall_removes_wiki_after_double_confirm(tmp_path, monkeypatch):
    """uninstall deletes wiki and registry entry after both confirmations."""
    import synthadoc.cli.install as install_mod
    dest = tmp_path / "my-wiki"
    dest.mkdir()
    (dest / "wiki").mkdir()
    monkeypatch.setattr(install_mod, "_REGISTRY", tmp_path / "wikis.json")
    install_mod._write_registry({"my-wiki": {"path": str(dest), "demo": None, "installed": "2026-04-09"}})

    # CliRunner input: first prompt "y", second prompt the wiki name
    result = runner.invoke(app, ["uninstall", "my-wiki"], input="y\nmy-wiki\n")
    assert result.exit_code == 0, result.output
    assert not dest.exists()
    assert "my-wiki" not in install_mod._read_registry()


def test_uninstall_aborts_on_wrong_name(tmp_path, monkeypatch):
    """uninstall aborts without deleting when typed name doesn't match."""
    import synthadoc.cli.install as install_mod
    dest = tmp_path / "my-wiki"
    dest.mkdir()
    monkeypatch.setattr(install_mod, "_REGISTRY", tmp_path / "wikis.json")
    install_mod._write_registry({"my-wiki": {"path": str(dest), "demo": None, "installed": "2026-04-09"}})

    result = runner.invoke(app, ["uninstall", "my-wiki"], input="y\nwrong-name\n")
    assert result.exit_code != 0
    assert dest.exists()


def test_uninstall_not_registered_shows_manual_instructions(tmp_path, monkeypatch):
    """uninstall of unregistered wiki prints path-of-manual-deletion instructions."""
    import synthadoc.cli.install as install_mod
    monkeypatch.setattr(install_mod, "_REGISTRY", tmp_path / "wikis.json")

    result = runner.invoke(app, ["uninstall", "ghost-wiki"])
    assert result.exit_code != 0
    assert "rm -rf" in result.output or "Remove-Item" in result.output


# ---------------------------------------------------------------------------
# resolve_wiki_path
# ---------------------------------------------------------------------------

def test_resolve_wiki_path_uses_registry(tmp_path, monkeypatch):
    """A registered wiki name resolves to its recorded path, not a relative dir."""
    import synthadoc.cli.install as install_mod
    monkeypatch.setattr(install_mod, "_REGISTRY", tmp_path / "wikis.json")
    install_mod._write_registry({
        "my-wiki": {"path": str(tmp_path / "actual-location"), "demo": None, "installed": "2026-04-09"}
    })
    result = install_mod.resolve_wiki_path("my-wiki")
    assert result == tmp_path / "actual-location"


def test_resolve_wiki_path_falls_back_to_filesystem(tmp_path, monkeypatch):
    """An unregistered value is returned as-is (filesystem path)."""
    import synthadoc.cli.install as install_mod
    monkeypatch.setattr(install_mod, "_REGISTRY", tmp_path / "wikis.json")
    result = install_mod.resolve_wiki_path(str(tmp_path / "some-dir"))
    assert result == tmp_path / "some-dir"


# ---------------------------------------------------------------------------
# demo list
# ---------------------------------------------------------------------------

def test_demo_list_shows_available_templates(tmp_path, monkeypatch):
    """demo list shows known demo names and marks installed ones."""
    import synthadoc.cli.install as install_mod
    monkeypatch.setattr(install_mod, "_DEMOS", {"history-of-computing": tmp_path})
    monkeypatch.setattr(install_mod, "_REGISTRY", tmp_path / "wikis.json")
    install_mod._write_registry({
        "history-of-computing": {"path": str(tmp_path / "history-of-computing"), "demo": "history-of-computing", "installed": "2026-04-09"}
    })

    result = runner.invoke(app, ["demo", "list"])
    assert result.exit_code == 0
    assert "history-of-computing" in result.output
    assert "installed" in result.output.lower()
