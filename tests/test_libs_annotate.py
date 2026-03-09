"""Tests for libs/ -- annotate_part public API."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from hive.db.models import Annotation, Base, Library, LibraryMember, Part
from hive.libs import annotate_part, tag_libraries
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


@pytest.fixture
async def cds_part(db_session):
    seq = "ATGAAAGCCTAA"
    part = Part(
        sequence_hash=hash_sequence(seq),
        sequence=seq, molecule="DNA", length=len(seq),
    )
    db_session.add(part)
    await db_session.flush()
    return part


class TestAnnotatePart:
    async def test_creates_type_annotation(self, db_session, cds_part):
        await annotate_part(db_session, cds_part.id, "CDS", cds_part.sequence)
        await db_session.flush()

        anns = (await db_session.execute(
            select(Annotation).where(
                Annotation.part_id == cds_part.id, Annotation.key == "type",
            )
        )).scalars().all()
        assert len(anns) == 1
        assert anns[0].value == "CDS"
        assert anns[0].source == "native"

    async def test_creates_computed_annotations(self, db_session, cds_part):
        await annotate_part(db_session, cds_part.id, "CDS", cds_part.sequence)
        await db_session.flush()

        anns = (await db_session.execute(
            select(Annotation).where(
                Annotation.part_id == cds_part.id, Annotation.source == "computed",
            )
        )).scalars().all()
        keys = {a.key for a in anns}
        assert "gc_content" in keys
        assert "orf_status" in keys
        assert "length" in keys

    async def test_cds_orf_status(self, db_session, cds_part):
        await annotate_part(db_session, cds_part.id, "CDS", cds_part.sequence)
        await db_session.flush()

        orf = (await db_session.execute(
            select(Annotation).where(
                Annotation.part_id == cds_part.id, Annotation.key == "orf_status",
            )
        )).scalar_one()
        assert orf.value == "complete"

    async def test_tags_library(self, db_session, cds_part):
        await annotate_part(db_session, cds_part.id, "CDS", cds_part.sequence)
        await db_session.flush()

        lib = (await db_session.execute(
            select(Library).where(Library.name == "CDS")
        )).scalar_one()
        member = (await db_session.execute(
            select(LibraryMember).where(
                LibraryMember.library_id == lib.id,
                LibraryMember.part_id == cds_part.id,
            )
        )).scalar_one()
        assert member is not None


class TestTagLibraries:
    async def test_unknown_type_no_library(self, db_session, cds_part):
        await tag_libraries(db_session, cds_part.id, "unknown_type")
        await db_session.flush()

        libs = (await db_session.execute(select(Library))).scalars().all()
        assert len(libs) == 0

    async def test_promoter_creates_library(self, db_session, cds_part):
        await tag_libraries(db_session, cds_part.id, "promoter")
        await db_session.flush()

        lib = (await db_session.execute(
            select(Library).where(Library.name == "Promoters")
        )).scalar_one()
        assert lib.source == "native"
