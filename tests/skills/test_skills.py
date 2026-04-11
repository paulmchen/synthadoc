# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Paul Chen / axoviq.com
import pytest
from pathlib import Path


def test_all_builtin_skills_registered():
    from synthadoc.agents.skill_agent import SkillAgent
    agent = SkillAgent()
    names = [s.name for s in agent.list_skills()]
    for expected in ("pdf", "url", "markdown", "docx", "xlsx", "image"):
        assert expected in names


def test_detect_skill_by_extension():
    from synthadoc.agents.skill_agent import SkillAgent
    agent = SkillAgent()
    assert agent.detect_skill("paper.pdf").name == "pdf"
    assert agent.detect_skill("notes.md").name == "markdown"
    assert agent.detect_skill("report.docx").name == "docx"
    assert agent.detect_skill("data.xlsx").name == "xlsx"
    assert agent.detect_skill("photo.png").name == "image"


def test_detect_skill_by_url_prefix():
    from synthadoc.agents.skill_agent import SkillAgent
    agent = SkillAgent()
    assert agent.detect_skill("https://example.com/page").name == "url"
    assert agent.detect_skill("http://example.com").name == "url"


def test_unknown_extension_raises():
    from synthadoc.agents.skill_agent import SkillAgent, SkillNotFoundError
    agent = SkillAgent()
    with pytest.raises(SkillNotFoundError):
        agent.detect_skill("file.xyz")


def test_tier1_metadata_always_available():
    from synthadoc.agents.skill_agent import SkillAgent
    agent = SkillAgent()
    for meta in agent.list_skills():
        assert meta.name
        assert meta.description


@pytest.mark.asyncio
async def test_markdown_skill_extracts(tmp_path):
    from synthadoc.skills.markdown.scripts.main import MarkdownSkill
    f = tmp_path / "note.md"
    f.write_text("# Hello\n\nWorld content here.", encoding="utf-8")
    result = await MarkdownSkill().extract(str(f))
    assert "Hello" in result.text and "World" in result.text


@pytest.mark.asyncio
async def test_url_skill_fetches(tmp_path):
    import respx, httpx
    from synthadoc.skills.url.scripts.main import UrlSkill
    with respx.mock:
        respx.get("https://example.com/").mock(
            return_value=httpx.Response(200,
                text="<html><body><p>Hello from web</p></body></html>")
        )
        result = await UrlSkill().extract("https://example.com/")
    assert "Hello from web" in result.text


@pytest.mark.asyncio
async def test_url_skill_raises_on_404():
    import respx, httpx
    from synthadoc.skills.url.scripts.main import UrlSkill
    with respx.mock:
        respx.get("https://example.com/missing").mock(return_value=httpx.Response(404))
        with pytest.raises(Exception, match="404"):
            await UrlSkill().extract("https://example.com/missing")


@pytest.mark.asyncio
async def test_url_skill_raises_on_connection_error():
    import respx, httpx
    from synthadoc.skills.url.scripts.main import UrlSkill
    with respx.mock:
        respx.get("https://unreachable.example/").mock(side_effect=httpx.ConnectError("refused"))
        with pytest.raises(httpx.ConnectError):
            await UrlSkill().extract("https://unreachable.example/")


def test_pip_skills_loaded_from_entry_points():
    """Skills registered via entry_points('synthadoc.skills') are auto-discovered."""
    from unittest.mock import MagicMock, patch
    from synthadoc.agents.skill_agent import SkillAgent
    from synthadoc.skills.base import BaseSkill, ExtractedContent, SkillMeta

    class FakeCustomSkill(BaseSkill):
        meta = SkillMeta(name="custom_pip", description="pip skill", extensions=[".xyz"])
        async def extract(self, source): return ExtractedContent("", source, {})

    ep = MagicMock()
    ep.load.return_value = FakeCustomSkill
    with patch("importlib.metadata.entry_points", return_value=[ep]):
        agent = SkillAgent()
    assert "custom_pip" in [s.name for s in agent.list_skills()]


def test_local_skill_loaded_from_skills_folder(tmp_path):
    """A .py file dropped in skills/ is discovered and registered without install."""
    from synthadoc.agents.skill_agent import SkillAgent

    skill_file = tmp_path / "custom_local.py"
    skill_file.write_text(
        "from synthadoc.skills.base import BaseSkill, ExtractedContent, SkillMeta\n"
        "class LocalSkill(BaseSkill):\n"
        "    meta = SkillMeta(name='local_csv', description='local', extensions=['.tsv'])\n"
        "    async def extract(self, source): return ExtractedContent('', source, {})\n",
        encoding="utf-8",
    )
    agent = SkillAgent(extra_dirs=[tmp_path])
    assert "local_csv" in [s.name for s in agent.list_skills()]


def test_local_skill_overrides_builtin(tmp_path):
    """A local skill with the same name as a built-in takes precedence."""
    from synthadoc.agents.skill_agent import SkillAgent

    skill_file = tmp_path / "override_pdf.py"
    skill_file.write_text(
        "from synthadoc.skills.base import BaseSkill, ExtractedContent, SkillMeta\n"
        "class OverridePdf(BaseSkill):\n"
        "    meta = SkillMeta(name='pdf', description='override', extensions=['.pdf'])\n"
        "    async def extract(self, source): return ExtractedContent('custom', source, {})\n",
        encoding="utf-8",
    )
    agent = SkillAgent(extra_dirs=[tmp_path])
    skill = agent.get_skill("pdf")
    assert skill.meta.description == "override"


def test_local_skill_with_syntax_error_is_skipped(tmp_path, caplog):
    """Broken local skill files log a warning and do not crash the agent."""
    import logging
    from synthadoc.agents.skill_agent import SkillAgent

    bad_file = tmp_path / "broken.py"
    bad_file.write_text("this is not valid python !!!", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        agent = SkillAgent(extra_dirs=[tmp_path])
    assert any("broken.py" in r.message for r in caplog.records)
    assert "pdf" in [s.name for s in agent.list_skills()]   # built-ins still registered


def test_local_file_not_subclassing_baseskill_is_skipped(tmp_path, caplog):
    """A .py file in skills/ that doesn't subclass BaseSkill is silently skipped."""
    import logging
    from synthadoc.agents.skill_agent import SkillAgent

    bad_file = tmp_path / "notaskill.py"
    bad_file.write_text("class NotASkill:\n    pass\n", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        agent = SkillAgent(extra_dirs=[tmp_path])
    assert "notaskill" not in [s.name for s in agent.list_skills()]


@pytest.mark.asyncio
async def test_pdf_skill_cjk_fallback(tmp_path, monkeypatch):
    """PdfSkill falls back to pdfminer when pypdf yields too little text."""
    from synthadoc.skills.pdf.scripts.main import PdfSkill
    import synthadoc.skills.pdf.scripts.main as pdf_mod

    # Simulate pypdf returning nearly nothing (typical CJK font failure)
    def fake_pypdf(self, source):
        return ("x", 5)  # 1 char for 5 pages — below threshold

    monkeypatch.setattr(PdfSkill, "_extract_pypdf", fake_pypdf)

    # Simulate pdfminer returning the real Chinese text
    def fake_pdfminer(self, source):
        return "人工智能是计算机科学的一个重要分支。"

    monkeypatch.setattr(PdfSkill, "_extract_pdfminer", fake_pdfminer)

    dummy_pdf = tmp_path / "test.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4")  # minimal placeholder
    result = await PdfSkill().extract(str(dummy_pdf))
    assert "人工智能" in result.text


@pytest.mark.asyncio
async def test_pdf_skill_no_fallback_when_pypdf_succeeds(tmp_path, monkeypatch):
    """PdfSkill does NOT call pdfminer when pypdf returns enough text."""
    from synthadoc.skills.pdf.scripts.main import PdfSkill

    def fake_pypdf(self, source):
        return ("A" * 500, 3)  # well above threshold

    monkeypatch.setattr(PdfSkill, "_extract_pypdf", fake_pypdf)

    called = []
    def fake_pdfminer(self, source):
        called.append(True)
        return "pdfminer text"

    monkeypatch.setattr(PdfSkill, "_extract_pdfminer", fake_pdfminer)

    dummy_pdf = tmp_path / "test.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4")
    await PdfSkill().extract(str(dummy_pdf))
    assert not called, "pdfminer should not be called when pypdf yields sufficient text"


def test_tier2_instantiates_only_on_demand():
    """get_skill() should not be called during SkillAgent init — only on demand."""
    from synthadoc.agents.skill_agent import SkillAgent
    agent = SkillAgent()
    metas = agent.list_skills()
    assert all(hasattr(m, "name") for m in metas)
    skill = agent.get_skill("pdf")
    assert skill is not None


def test_tier3_resource_loaded_lazily(tmp_path):
    """get_resource() loads a file from the skill's resources/ dir on first call only."""
    from synthadoc.skills.base import BaseSkill, ExtractedContent, SkillMeta

    resources_dir = tmp_path / "resources"
    resources_dir.mkdir()
    (resources_dir / "prompt.md").write_text("# Vision prompt", encoding="utf-8")

    class ResourceSkill(BaseSkill):
        meta = SkillMeta(name="res", description="d", extensions=[".res"])
        async def extract(self, source): return ExtractedContent("", source, {})

    skill = ResourceSkill()
    skill._resources_dir = resources_dir
    text = skill.get_resource("prompt.md")
    assert text == "# Vision prompt"
    # second call uses cache — file can be deleted
    (resources_dir / "prompt.md").unlink()
    assert skill.get_resource("prompt.md") == "# Vision prompt"


def test_triggers_dataclass():
    from synthadoc.skills.base import Triggers
    t = Triggers(extensions=[".pdf"], intents=["research paper"])
    assert ".pdf" in t.extensions
    assert "research paper" in t.intents


def test_skillmeta_with_triggers():
    from synthadoc.skills.base import SkillMeta, Triggers
    m = SkillMeta(
        name="pdf", version="1.0", description="PDF skill",
        entry_script="scripts/main.py", entry_class="PdfSkill",
        triggers=Triggers(extensions=[".pdf"], intents=["document"]),
        requires=["pypdf"],
    )
    assert m.triggers.extensions == [".pdf"]
    assert m.version == "1.0"


def test_skillmeta_backwards_compat_extensions():
    """Old-style SkillMeta(extensions=[...]) still works without triggers."""
    from synthadoc.skills.base import SkillMeta
    m = SkillMeta(name="old", description="old skill", extensions=[".old"])
    assert ".old" in m.triggers.extensions


def test_get_resource_searches_assets_then_references(tmp_path):
    from synthadoc.skills.base import BaseSkill, ExtractedContent, SkillMeta

    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "config.json").write_text('{"key": "val"}', encoding="utf-8")
    (tmp_path / "references").mkdir()
    (tmp_path / "references" / "notes.md").write_text("# Notes", encoding="utf-8")

    class TestSkill(BaseSkill):
        meta = SkillMeta(name="t", description="t", extensions=[".t"])
        async def extract(self, source): return ExtractedContent("", source, {})

    skill = TestSkill()
    skill.skill_dir = tmp_path
    assert '{"key": "val"}' in skill.get_resource("config.json")
    assert "# Notes" in skill.get_resource("notes.md")


def test_get_resource_cache_avoids_second_read(tmp_path):
    from synthadoc.skills.base import BaseSkill, ExtractedContent, SkillMeta

    (tmp_path / "assets").mkdir()
    f = tmp_path / "assets" / "data.txt"
    f.write_text("original", encoding="utf-8")

    class TestSkill(BaseSkill):
        meta = SkillMeta(name="t2", description="t2", extensions=[".t2"])
        async def extract(self, source): return ExtractedContent("", source, {})

    skill = TestSkill()
    skill.skill_dir = tmp_path
    skill.get_resource("data.txt")
    f.write_text("modified", encoding="utf-8")
    assert skill.get_resource("data.txt") == "original"  # served from cache
