"""Tests for libs/match -- variant detection on name collision."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from hive.db.models import Annotation, Base, Part, PartName
from hive.libs.match import detect_name_collision, flag_variant
from hive.utils import hash_sequence


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def _make_part(seq: str) -> Part:
    return Part(
        sequence_hash=hash_sequence(seq),
        sequence=seq, molecule="DNA", length=len(seq),
    )


class TestDetectNameCollision:
    async def test_no_collision(self, db_session):
        p1 = _make_part("ATGATGATG")
        db_session.add(p1)
        await db_session.flush()
        db_session.add(PartName(part_id=p1.id, name="GFP", source="file"))
        await db_session.flush()

        collisions = await detect_name_collision(db_session, p1.id, "GFP")
        assert collisions == []

    async def test_same_name_different_sequence(self, db_session):
        p1 = _make_part("ATGATGATG")
        p2 = _make_part("GCGGCGGCG")
        db_session.add_all([p1, p2])
        await db_session.flush()
        db_session.add(PartName(part_id=p1.id, name="GFP", source="file"))
        db_session.add(PartName(part_id=p2.id, name="GFP", source="file"))
        await db_session.flush()

        collisions = await detect_name_collision(db_session, p1.id, "GFP")
        assert collisions == [p2.id]

    async def test_different_name_no_collision(self, db_session):
        p1 = _make_part("ATGATGATG")
        p2 = _make_part("GCGGCGGCG")
        db_session.add_all([p1, p2])
        await db_session.flush()
        db_session.add(PartName(part_id=p1.id, name="GFP", source="file"))
        db_session.add(PartName(part_id=p2.id, name="RFP", source="file"))
        await db_session.flush()

        collisions = await detect_name_collision(db_session, p1.id, "GFP")
        assert collisions == []

    async def test_multiple_collisions(self, db_session):
        p1 = _make_part("AAAA")
        p2 = _make_part("CCCC")
        p3 = _make_part("GGGG")
        db_session.add_all([p1, p2, p3])
        await db_session.flush()
        for p in [p1, p2, p3]:
            db_session.add(PartName(part_id=p.id, name="AmpR", source="file"))
        await db_session.flush()

        collisions = await detect_name_collision(db_session, p1.id, "AmpR")
        assert sorted(collisions) == sorted([p2.id, p3.id])


class TestFlagVariant:
    async def test_creates_annotation(self, db_session):
        p1 = _make_part("ATGATGATG")
        db_session.add(p1)
        await db_session.flush()

        await flag_variant(db_session, p1.id, [10, 20])
        await db_session.flush()

        ann = (await db_session.execute(
            select(Annotation).where(
                Annotation.part_id == p1.id, Annotation.key == "variant_of",
            )
        )).scalar_one()
        assert ann.value == "10,20"
        assert ann.source == "computed"

    async def test_empty_list_no_annotation(self, db_session):
        p1 = _make_part("ATGATGATG")
        db_session.add(p1)
        await db_session.flush()

        await flag_variant(db_session, p1.id, [])
        await db_session.flush()

        anns = (await db_session.execute(
            select(Annotation).where(Annotation.part_id == p1.id)
        )).scalars().all()
        assert len(anns) == 0

    async def test_idempotent(self, db_session):
        p1 = _make_part("ATGATGATG")
        db_session.add(p1)
        await db_session.flush()

        await flag_variant(db_session, p1.id, [10])
        await flag_variant(db_session, p1.id, [10])
        await db_session.flush()

        anns = (await db_session.execute(
            select(Annotation).where(
                Annotation.part_id == p1.id, Annotation.key == "variant_of",
            )
        )).scalars().all()
        assert len(anns) == 1
