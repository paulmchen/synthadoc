# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest, yaml, sys
from pathlib import Path


def _local_skill(wiki: Path, name: str, extensions=None, intents=None,
                 description="local") -> Path:
    skill_dir = wiki / "skills" / name
    (skill_dir / "scripts").mkdir(parents=True)
    fm = {
        "name": name, "version": "1.0", "description": description,
        "entry": {"script": "scripts/main.py", "class": f"{name.title()}Skill"},
        "triggers": {"extensions": extensions or [], "intents": intents or []},
        "requires": [],
    }
    (skill_dir / "SKILL.md").write_text(f"---\n{yaml.dump(fm)}---\n", encoding="utf-8")
    (skill_dir / "scripts" / "main.py").write_text(
        f"from synthadoc.skills.base import BaseSkill, ExtractedContent\n"
        f"class {name.title()}Skill(BaseSkill):\n"
        f"    async def extract(self, s): return ExtractedContent('{name}', s, {{}})\n",
        encoding="utf-8",
    )
    return skill_dir


def test_all_builtin_skills_registered(tmp_wiki):
    from synthadoc.agents.skill_agent import SkillAgent
    agent = SkillAgent(wiki_root=tmp_wiki)
    names = [s.name for s in agent.list_skills()]
    for expected in ("pdf", "url", "markdown", "docx", "xlsx", "image", "web_search"):
        assert expected in names, f"'{expected}' missing from {names}"


def test_intent_dispatch_by_extension(tmp_wiki):
    from synthadoc.agents.skill_agent import SkillAgent
    agent = SkillAgent(wiki_root=tmp_wiki)
    assert agent.detect_skill("paper.pdf").name == "pdf"
    assert agent.detect_skill("notes.md").name == "markdown"
    assert agent.detect_skill("report.docx").name == "docx"
    assert agent.detect_skill("data.xlsx").name == "xlsx"
    assert agent.detect_skill("photo.png").name == "image"
    assert agent.detect_skill("https://example.com").name == "url"
    assert agent.detect_skill("http://example.com").name == "url"


def test_intent_dispatch_by_phrase(tmp_wiki):
    from synthadoc.agents.skill_agent import SkillAgent
    agent = SkillAgent(wiki_root=tmp_wiki)
    assert agent.detect_skill("search for recent AI papers").name == "web_search"
    assert agent.detect_skill("find on the web: quantum computing").name == "web_search"
    assert agent.detect_skill("web search quantum physics").name == "web_search"


def test_intent_dispatch_no_match_raises(tmp_wiki):
    from synthadoc.agents.skill_agent import SkillAgent, SkillNotFoundError
    agent = SkillAgent(wiki_root=tmp_wiki)
    with pytest.raises(SkillNotFoundError):
        agent.detect_skill("file.xyz_unknown_format")


def test_local_skill_overrides_builtin(tmp_wiki):
    _local_skill(tmp_wiki, "pdf", extensions=[".pdf"], description="local override")
    from synthadoc.agents.skill_agent import SkillAgent
    agent = SkillAgent(wiki_root=tmp_wiki)
    assert agent.detect_skill("doc.pdf").description == "local override"


def test_tier1_list_no_python_import(tmp_wiki):
    before = set(sys.modules.keys())
    from synthadoc.agents.skill_agent import SkillAgent
    agent = SkillAgent(wiki_root=tmp_wiki)
    agent.list_skills()
    new_mods = set(sys.modules.keys()) - before
    assert not any("skills.pdf.scripts" in m for m in new_mods)


def test_tier2_lazy_load(tmp_wiki):
    from synthadoc.agents.skill_agent import SkillAgent
    agent = SkillAgent(wiki_root=tmp_wiki)
    # PDF scripts not imported yet
    skill = agent.get_skill("pdf")
    assert skill is not None


def test_tier3_get_resource(tmp_wiki):
    from synthadoc.agents.skill_agent import SkillAgent
    agent = SkillAgent(wiki_root=tmp_wiki)
    skill = agent.get_skill("pdf")
    content = skill.get_resource("cjk-notes.md")
    assert len(content) > 0


def test_missing_requires_raises_clear_error(tmp_wiki):
    _local_skill(tmp_wiki, "needs_fake_pkg", extensions=[".fake"])
    # Add a bogus requires to the SKILL.md
    skill_dir = tmp_wiki / "skills" / "needs_fake_pkg"
    md = skill_dir / "SKILL.md"
    parts = md.read_text().split("---", 2)
    fm = yaml.safe_load(parts[1])
    fm["requires"] = ["this-package-does-not-exist-xyz"]
    md.write_text(f"---\n{yaml.dump(fm)}---\n", encoding="utf-8")
    from synthadoc.agents.skill_agent import SkillAgent
    agent = SkillAgent(wiki_root=tmp_wiki)
    with pytest.raises(ImportError, match="needs_fake_pkg"):
        agent.get_skill("needs_fake_pkg")


def test_registry_cache_written(tmp_wiki):
    from synthadoc.agents.skill_agent import SkillAgent
    SkillAgent(wiki_root=tmp_wiki)
    cache = tmp_wiki / ".synthadoc" / "skill_registry.json"
    assert cache.exists()


def test_pip_entry_point_skill_loaded(tmp_wiki):
    from unittest.mock import patch
    # _local_skill creates: tmp_wiki / "skills" / "_pip_skill_standalone"
    skill_dir = _local_skill(tmp_wiki, "_pip_skill_standalone", extensions=[".psk"],
                             description="pip installed")
    from synthadoc.agents.skill_agent import SkillAgent
    with patch("synthadoc.agents.skill_agent._entry_point_skill_dirs",
               return_value=[skill_dir]):
        agent = SkillAgent(wiki_root=tmp_wiki)
    assert "_pip_skill_standalone" in [s.name for s in agent.list_skills()]
