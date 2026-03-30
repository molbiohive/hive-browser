"""Tests for SkillLibrary."""

from pathlib import Path

from hive.skills.library import SkillLibrary, _extract_when

SAMPLE_MD = """\
# My Skill

## When
User wants to do something specific.

## Workflow
1. Step one.
2. Step two.

## Pitfalls
- Watch out for X.
"""


class TestExtractWhen:
    def test_extracts_section(self):
        assert _extract_when(SAMPLE_MD) == "User wants to do something specific."

    def test_empty_when_missing(self):
        assert _extract_when("# No when section here\n## Other\nstuff") == ""

    def test_multiline_when(self):
        md = "## When\nLine one.\nLine two.\n\n## Next"
        assert _extract_when(md) == "Line one.\nLine two."

    def test_when_at_end(self):
        md = "## When\nLast section with no next heading."
        assert _extract_when(md) == "Last section with no next heading."


class TestSkillLibrary:
    def test_load_from_dir(self, tmp_path):
        (tmp_path / "alpha.md").write_text("# Alpha\n## When\nDo alpha.\n## Workflow\n1. Go.")
        (tmp_path / "beta.md").write_text("# Beta\n## When\nDo beta.\n## Workflow\n1. Go.")
        lib = SkillLibrary(tmp_path)
        assert len(lib) == 2
        assert set(lib.names()) == {"alpha", "beta"}

    def test_catalog(self, tmp_path):
        (tmp_path / "test.md").write_text("# Test\n## When\nTrigger condition.\n## End")
        lib = SkillLibrary(tmp_path)
        cat = lib.catalog()
        assert len(cat) == 1
        assert cat[0]["name"] == "test"
        assert cat[0]["when"] == "Trigger condition."

    def test_read_existing(self, tmp_path):
        content = "# Skill\n## When\nAlways.\n## Done"
        (tmp_path / "skill.md").write_text(content)
        lib = SkillLibrary(tmp_path)
        assert lib.read("skill") == content

    def test_read_missing(self, tmp_path):
        lib = SkillLibrary(tmp_path)
        assert lib.read("nonexistent") is None

    def test_empty_dir(self, tmp_path):
        lib = SkillLibrary(tmp_path)
        assert len(lib) == 0
        assert lib.catalog() == []

    def test_missing_dir(self, tmp_path):
        lib = SkillLibrary(tmp_path / "does_not_exist")
        assert len(lib) == 0

    def test_ignores_non_md(self, tmp_path):
        (tmp_path / "readme.txt").write_text("not a skill")
        (tmp_path / "skill.md").write_text("# Skill\n## When\nYes.\n## End")
        (tmp_path / "__init__.py").write_text("")
        lib = SkillLibrary(tmp_path)
        assert len(lib) == 1
        assert lib.names() == ["skill"]

    def test_no_args_empty(self):
        """SkillLibrary() with no args yields empty library."""
        lib = SkillLibrary()
        assert len(lib) == 0

    def test_load_from_data(self):
        """SkillLibrary with skills_data loads from dicts."""
        data = [
            {"name": "alpha", "content": "# Alpha\n## When\nDo alpha.\n## End"},
            {"name": "beta", "content": "# Beta\n## When\nDo beta.\n## End"},
        ]
        lib = SkillLibrary(skills_data=data)
        assert len(lib) == 2
        assert set(lib.names()) == {"alpha", "beta"}
        assert lib.read("alpha").startswith("# Alpha")

    def test_reload(self):
        """reload() replaces all skills."""
        lib = SkillLibrary(skills_data=[
            {"name": "old", "content": "# Old\n## When\nBefore.\n## End"},
        ])
        assert len(lib) == 1
        lib.reload([
            {"name": "new", "content": "# New\n## When\nAfter.\n## End"},
        ])
        assert len(lib) == 1
        assert lib.names() == ["new"]
        assert lib.read("old") is None
