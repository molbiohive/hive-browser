"""Tests for libs/loader -- import/export part library JSON envelopes."""

import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from hive.db.models import (
    Annotation,
    Base,
    Library,
    LibraryMember,
    Part,
    PartName,
)
from hive.libs.loader import export_lib, import_lib, validate_envelope


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


LIBRARY_JSON = {
    "type": "library",
    "version": 1,
    "name": "Test Promoters",
    "description": "Test promoter collection",
    "data": [
        {
            "sequence": "TATAATGCAGCTGGCACGACAG",
            "molecule": "DNA",
            "names": [{"name": "T7", "source": "file"}],
            "annotations": [
                {"key": "type", "value": "promoter", "source": "native"},
            ],
        },
        {
            "sequence": "TTGACAGCTAGCTCAGTCCTAGG",
            "molecule": "DNA",
            "names": ["BBa_J23100"],
            "annotations": [
                {"key": "type", "value": "promoter", "source": "native"},
                {"key": "strength", "value": "strong", "source": "manual"},
            ],
        },
    ],
}


class TestValidateEnvelope:
    def test_valid(self):
        typ, ver, data = validate_envelope(LIBRARY_JSON)
        assert typ == "library"
        assert ver == 1
        assert len(data) == 2

    def test_missing_type(self):
        with pytest.raises(ValueError, match="Missing required field: type"):
            validate_envelope({"version": 1, "data": []})

    def test_missing_version(self):
        with pytest.raises(ValueError, match="Missing required field: version"):
            validate_envelope({"type": "x", "data": []})

    def test_missing_data(self):
        with pytest.raises(ValueError, match="Missing required field: data"):
            validate_envelope({"type": "x", "version": 1})

    def test_bad_version(self):
        with pytest.raises(ValueError, match="positive integer"):
            validate_envelope({"type": "x", "version": 0, "data": []})

    def test_not_dict(self):
        with pytest.raises(ValueError, match="JSON object"):
            validate_envelope("not a dict")

    def test_data_not_list(self):
        with pytest.raises(ValueError, match="must be a list"):
            validate_envelope({"type": "x", "version": 1, "data": "nope"})


class TestImportLibrary:
    async def test_import_creates_library_and_parts(self, db_session, tmp_path):
        path = tmp_path / "lib.json"
        path.write_text(json.dumps(LIBRARY_JSON))

        result = await import_lib(db_session, path)
        await db_session.commit()

        assert result["type"] == "library"
        assert result["name"] == "Test Promoters"
        assert result["parts_created"] == 2

        lib = (await db_session.execute(
            select(Library).where(Library.name == "Test Promoters")
        )).scalar_one()
        assert lib.source == "native"

        members = (await db_session.execute(
            select(LibraryMember).where(LibraryMember.library_id == lib.id)
        )).scalars().all()
        assert len(members) == 2

    async def test_import_creates_names_and_annotations(self, db_session, tmp_path):
        path = tmp_path / "lib.json"
        path.write_text(json.dumps(LIBRARY_JSON))

        await import_lib(db_session, path)
        await db_session.commit()

        names = (await db_session.execute(select(PartName))).scalars().all()
        name_set = {n.name for n in names}
        assert "T7" in name_set
        assert "BBa_J23100" in name_set

        anns = (await db_session.execute(select(Annotation))).scalars().all()
        assert len(anns) == 3  # 1 + 2

    async def test_import_idempotent(self, db_session, tmp_path):
        path = tmp_path / "lib.json"
        path.write_text(json.dumps(LIBRARY_JSON))

        await import_lib(db_session, path)
        await db_session.commit()
        result = await import_lib(db_session, path)
        await db_session.commit()

        assert result["parts_existing"] == 2
        assert result["parts_created"] == 0

    async def test_wrong_type_rejected(self, db_session, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text(json.dumps({"type": "enzymes", "version": 1, "data": []}))
        with pytest.raises(ValueError, match="Expected type 'library'"):
            await import_lib(db_session, path)


class TestExportLibrary:
    async def test_export_roundtrip(self, db_session, tmp_path):
        src = tmp_path / "in.json"
        src.write_text(json.dumps(LIBRARY_JSON))
        await import_lib(db_session, src)
        await db_session.commit()

        out = tmp_path / "out.json"
        await export_lib(db_session, "Test Promoters", out)

        exported = json.loads(out.read_text())
        assert exported["type"] == "library"
        assert exported["name"] == "Test Promoters"
        assert len(exported["data"]) == 2
        seqs = {e["sequence"] for e in exported["data"]}
        assert "TATAATGCAGCTGGCACGACAG" in seqs

    async def test_export_not_found(self, db_session, tmp_path):
        with pytest.raises(ValueError, match="not found"):
            await export_lib(db_session, "NonExistent", tmp_path / "out.json")
