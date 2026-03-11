"""Tests for cloning/collections -- collection CRUD and active resolvers."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from hive.cloning.collections import (
    create_collection,
    delete_collection,
    get_active_enzyme_names,
    get_collection,
    list_collections,
    update_collection,
)
from hive.db.models import Base, Collection, User


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


async def _make_user(session, username="testuser"):
    user = User(username=username, slug=username, token=f"tok_{username}", preferences={})
    session.add(user)
    await session.flush()
    return user


class TestCollectionCRUD:
    async def test_create_and_get(self, db_session):
        col = await create_collection(
            db_session, name="Common Enzymes", set_type="enzymes",
            items=["EcoRI", "BamHI", "HindIII"],
        )
        await db_session.commit()

        fetched = await get_collection(db_session, col.id)
        assert fetched is not None
        assert fetched.name == "Common Enzymes"
        assert fetched.set_type == "enzymes"
        assert fetched.items == ["EcoRI", "BamHI", "HindIII"]

    async def test_create_invalid_type(self, db_session):
        with pytest.raises(ValueError, match="Invalid set_type"):
            await create_collection(db_session, name="Bad", set_type="invalid", items=[])

    async def test_list_by_type(self, db_session):
        await create_collection(db_session, name="E1", set_type="enzymes", items=["EcoRI"])
        await create_collection(db_session, name="P1", set_type="primers", items=[1, 2])
        await create_collection(db_session, name="E2", set_type="enzymes", items=["BamHI"])
        await db_session.commit()

        enzymes = await list_collections(db_session, set_type="enzymes")
        assert len(enzymes) == 2

        primers = await list_collections(db_session, set_type="primers")
        assert len(primers) == 1

        all_cols = await list_collections(db_session)
        assert len(all_cols) == 3

    async def test_update(self, db_session):
        col = await create_collection(
            db_session, name="Old Name", set_type="enzymes", items=["EcoRI"],
        )
        await db_session.commit()

        updated = await update_collection(
            db_session, col.id, name="New Name", items=["EcoRI", "BamHI"],
        )
        assert updated.name == "New Name"
        assert updated.items == ["EcoRI", "BamHI"]

    async def test_update_not_found(self, db_session):
        with pytest.raises(ValueError, match="not found"):
            await update_collection(db_session, 999)

    async def test_delete(self, db_session):
        col = await create_collection(
            db_session, name="To Delete", set_type="enzymes", items=[],
        )
        await db_session.commit()

        assert await delete_collection(db_session, col.id) is True
        assert await get_collection(db_session, col.id) is None

    async def test_delete_not_found(self, db_session):
        assert await delete_collection(db_session, 999) is False

    async def test_default_flag(self, db_session):
        await create_collection(
            db_session, name="Custom", set_type="enzymes", items=["EcoRI"],
        )
        await create_collection(
            db_session, name="System Default", set_type="enzymes",
            items=["EcoRI", "BamHI"], is_default=True,
        )
        await db_session.commit()

        cols = await list_collections(db_session, set_type="enzymes")
        # Default should come first
        assert cols[0].name == "System Default"
        assert cols[0].is_default is True


class TestActiveResolvers:
    async def test_enzyme_names_with_collection(self, db_session):
        user = await _make_user(db_session)
        col = await create_collection(
            db_session, name="My Enzymes", set_type="enzymes",
            items=["EcoRI", "BamHI"],
        )
        user.preferences = {"enzyme_collection_id": col.id}
        await db_session.commit()

        names = await get_active_enzyme_names(db_session, user.id)
        assert names == ["EcoRI", "BamHI"]

    async def test_enzyme_names_no_pref(self, db_session):
        user = await _make_user(db_session)
        await db_session.commit()

        names = await get_active_enzyme_names(db_session, user.id)
        assert names is None  # means "use all"

    async def test_enzyme_names_no_user(self, db_session):
        names = await get_active_enzyme_names(db_session, None)
        assert names is None
