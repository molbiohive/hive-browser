"""Tests for database audit and cleanup operations."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from hive.admin.db import audit, dedupe, prune
from hive.db.models import Base, Feature, IndexedFile, Primer, Sequence

FIXTURES = Path(__file__).parent / "fixtures"


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


def _make_file(session, path="/tmp/test.dna", file_hash="abc123", status="active"):
    f = IndexedFile(
        file_path=path, file_hash=file_hash, format="dna",
        status=status, file_size=1000,
        file_mtime=datetime.now(UTC),
    )
    session.add(f)
    return f


async def _make_file_with_seq(session, path="/tmp/test.dna", file_hash="abc123",
                               seq_name="pTest", seq_text="ATGC"):
    f = _make_file(session, path=path, file_hash=file_hash)
    await session.flush()
    seq = Sequence(
        file_id=f.id, name=seq_name, size_bp=len(seq_text),
        topology="circular", sequence=seq_text,
    )
    session.add(seq)
    await session.flush()
    feat = Feature(
        seq_id=seq.id, name="GFP", type="CDS", start=1, end=4, strand=1,
    )
    session.add(feat)
    await session.commit()
    return f


class TestAudit:
    async def test_empty_db(self, db_session):
        result = await audit(db_session, "/tmp/watcher")
        assert result["totals"]["sequences"] == 0
        assert result["orphans"] == 0

    async def test_counts(self, db_session):
        await _make_file_with_seq(db_session, path="/tmp/a.dna", file_hash="h1")
        await _make_file_with_seq(db_session, path="/tmp/b.dna", file_hash="h2")
        result = await audit(db_session, "/tmp")
        assert result["totals"]["indexed_files"]["active"] == 2
        assert result["totals"]["sequences"] == 2
        assert result["totals"]["features"] == 2

    async def test_hash_duplicates(self, db_session):
        await _make_file_with_seq(db_session, path="/tmp/a.dna", file_hash="same")
        await _make_file_with_seq(db_session, path="/tmp/b.dna", file_hash="same")
        result = await audit(db_session, "/tmp")
        assert result["hash_duplicates"]["groups"] == 1
        assert result["hash_duplicates"]["files"] == 2

    async def test_verbose_details(self, db_session):
        await _make_file_with_seq(db_session, path="/tmp/a.dna", file_hash="same")
        await _make_file_with_seq(db_session, path="/tmp/b.dna", file_hash="same")
        result = await audit(db_session, "/tmp", verbose=True)
        assert len(result["hash_duplicate_details"]) == 1
        assert result["hash_duplicate_details"][0]["count"] == 2

    async def test_orphan_detection(self, db_session):
        # File path that doesn't exist on disk
        _make_file(db_session, path="/nonexistent/path/orphan.dna", file_hash="orph")
        await db_session.commit()
        result = await audit(db_session, "/tmp")
        assert result["orphans"] == 1


class TestDedupe:
    async def test_no_duplicates(self, db_session):
        await _make_file_with_seq(db_session, path="/tmp/a.dna", file_hash="h1")
        await _make_file_with_seq(db_session, path="/tmp/b.dna", file_hash="h2")
        result = await dedupe(db_session, dry_run=True)
        assert result["removed"] == 0

    async def test_dry_run(self, db_session):
        await _make_file_with_seq(db_session, path="/tmp/a.dna", file_hash="same")
        await _make_file_with_seq(db_session, path="/tmp/b.dna", file_hash="same")
        result = await dedupe(db_session, dry_run=True)
        assert result["removed"] == 1
        assert result["dry_run"] is True
        # Records should still be there
        count = len((await db_session.execute(
            select(IndexedFile).where(IndexedFile.status == "active")
        )).scalars().all())
        assert count == 2

    async def test_execute(self, db_session):
        await _make_file_with_seq(db_session, path="/tmp/a.dna", file_hash="same")
        await _make_file_with_seq(db_session, path="/tmp/b.dna", file_hash="same")
        result = await dedupe(db_session, dry_run=False)
        assert result["removed"] == 1
        assert result["dry_run"] is False
        # Only newest should remain
        remaining = (await db_session.execute(
            select(IndexedFile).where(IndexedFile.status == "active")
        )).scalars().all()
        assert len(remaining) == 1

    async def test_keeps_newest(self, db_session):
        await _make_file_with_seq(db_session, path="/tmp/old.dna", file_hash="same")
        await _make_file_with_seq(db_session, path="/tmp/new.dna", file_hash="same")
        result = await dedupe(db_session, dry_run=False)
        remaining = (await db_session.execute(
            select(IndexedFile).where(IndexedFile.status == "active")
        )).scalar_one()
        # Newest has highest id
        assert remaining.file_path == "/tmp/new.dna"
        assert result["details"][0]["path"] == "/tmp/old.dna"

    async def test_cascades_sequences(self, db_session):
        await _make_file_with_seq(db_session, path="/tmp/a.dna", file_hash="same")
        await _make_file_with_seq(db_session, path="/tmp/b.dna", file_hash="same")
        await dedupe(db_session, dry_run=False)
        seqs = (await db_session.execute(select(Sequence))).scalars().all()
        assert len(seqs) == 1


class TestPrune:
    async def test_no_orphans(self, db_session):
        # Use a real file that exists
        gb = FIXTURES / "test_plasmid.gb"
        _make_file(db_session, path=str(gb), file_hash="h1")
        await db_session.commit()
        result = await prune(db_session, str(FIXTURES))
        assert result["pruned"] == 0

    async def test_dry_run(self, db_session):
        _make_file(db_session, path="/nonexistent/orphan.dna", file_hash="orph")
        await db_session.commit()
        result = await prune(db_session, "/tmp", dry_run=True)
        assert result["pruned"] == 1
        assert result["dry_run"] is True
        # Record should still exist
        count = len((await db_session.execute(
            select(IndexedFile).where(IndexedFile.status == "active")
        )).scalars().all())
        assert count == 1

    async def test_execute(self, db_session):
        _make_file(db_session, path="/nonexistent/orphan.dna", file_hash="orph")
        await db_session.commit()
        result = await prune(db_session, "/tmp", dry_run=False, no_archive=True)
        assert result["pruned"] == 1
        remaining = (await db_session.execute(
            select(IndexedFile).where(IndexedFile.status == "active")
        )).scalars().all()
        assert len(remaining) == 0

    async def test_archive_jsonl(self, db_session, tmp_path):
        await _make_file_with_seq(
            db_session, path="/nonexistent/orphan.dna",
            file_hash="orph", seq_name="pOrphan", seq_text="ATGCATGC",
        )
        archive_dir = str(tmp_path / "archive")
        result = await prune(
            db_session, "/tmp", archive_dir=archive_dir, dry_run=False,
        )
        assert result["pruned"] == 1

        # Check JSONL archive file
        archive_files = list(Path(archive_dir).glob("prune-*.jsonl"))
        assert len(archive_files) == 1
        with open(archive_files[0]) as fh:
            lines = fh.readlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["name"] == "pOrphan"
        assert record["file_path"] == "/nonexistent/orphan.dna"
        assert record["size_bp"] == 8
        assert len(record["features"]) == 1
        assert record["features"][0]["name"] == "GFP"
        assert record["sequence_hash"] is not None
