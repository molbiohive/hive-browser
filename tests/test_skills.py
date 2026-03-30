"""Tests for skill service -- CRUD, bootstrap, validation, and SkillLibrary DB mode."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from hive.context.skills import (
    bootstrap_skills,
    create_skill,
    delete_skill,
    get_skill,
    list_skills,
    update_skill,
    validate_skill_content,
)
from hive.db import Base, Skill
from hive.skills.library import SkillLibrary


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


class TestSkillCRUD:
    async def test_create_and_get(self, db_session):
        sk = await create_skill(db_session, name="my_skill", content="# My Skill\n## When\nAlways.")
        await db_session.commit()

        fetched = await get_skill(db_session, sk.id)
        assert fetched is not None
        assert fetched.name == "my_skill"
        assert fetched.is_default is False

    async def test_list_ordered(self, db_session):
        await create_skill(db_session, name="zebra", content="z")
        await create_skill(db_session, name="alpha", content="a")
        db_session.add(Skill(name="builtin", content="b", is_default=True))
        await db_session.commit()

        skills = await list_skills(db_session)
        names = [s.name for s in skills]
        assert names[0] == "builtin"
        assert names[1] == "alpha"
        assert names[2] == "zebra"

    async def test_update(self, db_session):
        sk = await create_skill(db_session, name="old", content="old content")
        await db_session.commit()

        updated = await update_skill(db_session, sk.id, name="new", content="new content")
        assert updated.name == "new"
        assert updated.content == "new content"

    async def test_update_not_found(self, db_session):
        with pytest.raises(ValueError, match="not found"):
            await update_skill(db_session, 999, name="x")

    async def test_delete(self, db_session):
        sk = await create_skill(db_session, name="del_me", content="x")
        await db_session.commit()

        assert await delete_skill(db_session, sk.id) is True
        assert await get_skill(db_session, sk.id) is None

    async def test_delete_not_found(self, db_session):
        assert await delete_skill(db_session, 999) is False

    async def test_delete_rejects_default(self, db_session):
        db_session.add(Skill(name="builtin", content="x", is_default=True))
        await db_session.flush()

        skills = await list_skills(db_session)
        builtin = [s for s in skills if s.is_default][0]

        with pytest.raises(ValueError, match="Cannot delete built-in"):
            await delete_skill(db_session, builtin.id)


class TestBootstrap:
    async def test_seeds_from_extras(self, db_session):
        count = await bootstrap_skills(db_session)
        await db_session.commit()

        skills = await list_skills(db_session)
        assert len(skills) >= 1
        assert count == len(skills)
        assert all(s.is_default for s in skills)

    async def test_idempotent(self, db_session):
        count1 = await bootstrap_skills(db_session)
        await db_session.commit()

        count2 = await bootstrap_skills(db_session)
        await db_session.commit()

        assert count1 >= 1
        assert count2 == 0

        skills = await list_skills(db_session)
        assert len(skills) == count1


class TestValidation:
    def test_valid_skill(self):
        content = (
            "# My Skill\n"
            "## When\nDo stuff.\n"
            "## Tools\n- search\n"
            "## Workflow\n1. Step one\n"
            "## Report\n```python\nreport = {}\n```\n"
            "## Rules\n- Rule one\n"
        )
        assert validate_skill_content(content) == []

    def test_missing_title(self):
        content = "## When\nAlways.\n## Tools\n- x\n## Workflow\n1.\n## Report\nx\n## Rules\n- x"
        issues = validate_skill_content(content)
        assert any("# Title" in i for i in issues)

    def test_missing_sections(self):
        content = "# Title\n## When\nAlways."
        issues = validate_skill_content(content)
        assert any("Tools" in i for i in issues)
        assert any("Workflow" in i for i in issues)
        assert any("Report" in i for i in issues)
        assert any("Rules" in i for i in issues)
        assert not any("When" in i for i in issues)

    def test_empty_content(self):
        issues = validate_skill_content("")
        assert len(issues) == 6  # title + 5 sections

    def test_headers_with_spaces(self):
        content = (
            "# My Skill\n"
            "##  When \nDo stuff.\n"
            "## Tools \n- search\n"
            "##  Workflow\n1. Step\n"
            "## Report \nreport\n"
            "## Rules\n- rule\n"
        )
        assert validate_skill_content(content) == []


class TestSkillLibraryDB:
    def test_loads_from_data(self):
        data = [
            {"name": "alpha", "content": "# Alpha\n## When\nDo alpha.\n## End"},
            {"name": "beta", "content": "# Beta\n## When\nDo beta.\n## End"},
        ]
        lib = SkillLibrary(skills_data=data)
        assert len(lib) == 2
        assert set(lib.names()) == {"alpha", "beta"}
        cat = lib.catalog()
        assert cat[0]["when"] == "Do alpha."

    def test_reload_replaces(self):
        lib = SkillLibrary(skills_data=[{"name": "old", "content": "# Old\n## When\nBefore."}])
        assert lib.names() == ["old"]

        lib.reload([{"name": "new", "content": "# New\n## When\nAfter."}])
        assert lib.names() == ["new"]
        assert lib.read("old") is None
        assert lib.read("new") is not None
