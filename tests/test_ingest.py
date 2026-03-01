"""Tests for the ingestion pipeline — parse files and store in DB."""

from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from hive.db.models import Base, IndexedFile, Part, PartInstance, PartName, Sequence
from hive.watcher.ingest import extract_tags, ingest_file, remove_file
from hive.watcher.rules import MatchResult

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
async def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


class TestIngestGenbank:
    async def test_ingest_new_file(self, db_session):
        match = MatchResult(action="parse", parser="biopython", extract=None)
        result = await ingest_file(db_session, FIXTURES / "test_plasmid.gb", match)

        assert result is not None
        assert result.status == "active"
        assert result.format == "gb"

    async def test_creates_sequence(self, db_session):
        match = MatchResult(action="parse", parser="biopython", extract=None)
        await ingest_file(db_session, FIXTURES / "test_plasmid.gb", match)

        seqs = (await db_session.execute(select(Sequence))).scalars().all()
        assert len(seqs) == 1
        assert seqs[0].name == "pTest"
        assert seqs[0].topology == "circular"
        assert seqs[0].size_bp == 120

    async def test_creates_parts(self, db_session):
        match = MatchResult(action="parse", parser="biopython", extract=None)
        await ingest_file(db_session, FIXTURES / "test_plasmid.gb", match)

        # Parts should be created from features
        parts = (await db_session.execute(select(Part))).scalars().all()
        assert len(parts) >= 1

        # PartInstances link parts to the sequence
        pis = (await db_session.execute(select(PartInstance))).scalars().all()
        assert len(pis) == 3  # 3 features in test_plasmid.gb

        # PartNames should include feature names
        names = (await db_session.execute(select(PartName))).scalars().all()
        name_set = {n.name for n in names}
        assert "GFP_mini" in name_set
        assert "T7_promoter" in name_set

    async def test_sequence_has_hash_and_molecule(self, db_session):
        match = MatchResult(action="parse", parser="biopython", extract=None)
        await ingest_file(db_session, FIXTURES / "test_plasmid.gb", match)

        seq = (await db_session.execute(select(Sequence))).scalar_one()
        assert seq.sequence_hash != ""
        assert seq.molecule == "DNA"
        assert seq.length == 120

    async def test_skip_unchanged(self, db_session):
        match = MatchResult(action="parse", parser="biopython", extract=None)
        result1 = await ingest_file(db_session, FIXTURES / "test_plasmid.gb", match)
        result2 = await ingest_file(db_session, FIXTURES / "test_plasmid.gb", match)

        assert result1 is not None
        assert result2 is None  # Same hash, no re-index

    async def test_file_count(self, db_session):
        match = MatchResult(action="parse", parser="biopython", extract=None)
        await ingest_file(db_session, FIXTURES / "test_plasmid.gb", match)

        count = (await db_session.execute(
            select(func.count()).select_from(IndexedFile)
        )).scalar()
        assert count == 1


class TestIngestFasta:
    async def test_ingest_fasta(self, db_session):
        match = MatchResult(action="parse", parser="biopython", extract=None)
        result = await ingest_file(db_session, FIXTURES / "test_sequence.fasta", match)

        assert result is not None
        assert result.format == "fasta"

    async def test_fasta_no_parts(self, db_session):
        match = MatchResult(action="parse", parser="biopython", extract=None)
        await ingest_file(db_session, FIXTURES / "test_sequence.fasta", match)

        # FASTA files have no features, so no parts
        pis = (await db_session.execute(select(PartInstance))).scalars().all()
        assert len(pis) == 0

    async def test_fasta_sequence_data(self, db_session):
        match = MatchResult(action="parse", parser="biopython", extract=None)
        await ingest_file(db_session, FIXTURES / "test_sequence.fasta", match)

        seq = (await db_session.execute(select(Sequence))).scalar_one()
        assert seq.name == "GFP_coding_sequence"
        assert seq.topology == "linear"


class TestRemoveFile:
    async def test_remove_indexed_file(self, db_session):
        match = MatchResult(action="parse", parser="biopython", extract=None)
        path = FIXTURES / "test_plasmid.gb"
        await ingest_file(db_session, path, match)

        removed = await remove_file(db_session, path)
        assert removed is True

        # IndexedFile should be marked deleted
        f = (await db_session.execute(
            select(IndexedFile).where(IndexedFile.file_path == str(path))
        )).scalar_one()
        assert f.status == "deleted"

    async def test_remove_nonexistent(self, db_session):
        removed = await remove_file(db_session, Path("/nonexistent/file.gb"))
        assert removed is False

    async def test_remove_cascades_sequences(self, db_session):
        match = MatchResult(action="parse", parser="biopython", extract=None)
        path = FIXTURES / "test_plasmid.gb"
        await ingest_file(db_session, path, match)
        await remove_file(db_session, path)

        seqs = (await db_session.execute(select(Sequence))).scalars().all()
        assert len(seqs) == 0


class TestExtractTags:
    def test_basic_tags(self):
        tags = extract_tags(Path("/watcher/proj/sub/file.dna"), "/watcher")
        assert tags == ["proj", "sub"]

    def test_root_level_file(self):
        tags = extract_tags(Path("/watcher/file.dna"), "/watcher")
        assert tags == []

    def test_path_outside_root(self):
        tags = extract_tags(Path("/other/path/file.dna"), "/watcher")
        assert tags == []

    def test_deeply_nested(self):
        tags = extract_tags(Path("/watcher/lab/2024/q1/vectors/test.dna"), "/watcher")
        assert tags == ["lab", "2024", "q1", "vectors"]


class TestIngestWithTags:
    async def test_tags_populated(self, db_session):
        match = MatchResult(action="parse", parser="biopython", extract=None)
        await ingest_file(
            db_session, FIXTURES / "test_plasmid.gb", match,
            watcher_root=str(FIXTURES.parent),
        )
        seq = (await db_session.execute(select(Sequence))).scalar_one()
        meta = seq.meta or {}
        assert "tags" in meta
        assert "fixtures" in meta["tags"]

    async def test_no_tags_without_root(self, db_session):
        match = MatchResult(action="parse", parser="biopython", extract=None)
        await ingest_file(db_session, FIXTURES / "test_plasmid.gb", match)
        seq = (await db_session.execute(select(Sequence))).scalar_one()
        meta = seq.meta or {}
        assert "tags" not in meta


class TestMultipleFiles:
    async def test_ingest_multiple(self, db_session):
        match_gb = MatchResult(action="parse", parser="biopython", extract=None)
        match_fa = MatchResult(action="parse", parser="biopython", extract=None)

        await ingest_file(db_session, FIXTURES / "test_plasmid.gb", match_gb)
        await ingest_file(db_session, FIXTURES / "test_sequence.fasta", match_fa)

        files = (await db_session.execute(select(IndexedFile))).scalars().all()
        seqs = (await db_session.execute(select(Sequence))).scalars().all()

        assert len(files) == 2
        assert len(seqs) == 2
