"""Ingestion pipeline — parse file, upsert into database."""

import hashlib
import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from hive.db.models import Feature, IndexedFile, Primer, Sequence
from hive.parsers import BIOPYTHON_PARSERS, PARSERS
from hive.parsers.base import ParseResult
from hive.watcher.rules import MatchResult


def hash_file(path: Path) -> str:
    """SHA256 hash of file contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

logger = logging.getLogger(__name__)


def _resolve_parser(match: MatchResult, file_path: Path):
    """Resolve the correct parser function from match result and file extension."""
    parser_name = match.parser
    if parser_name == "biopython":
        ext = file_path.suffix.lstrip(".")
        parser_fn = BIOPYTHON_PARSERS.get(ext)
        if not parser_fn:
            raise ValueError(f"No biopython parser for extension: .{ext}")
        return parser_fn

    parser_fn = PARSERS.get(parser_name)
    if not parser_fn:
        raise ValueError(f"Unknown parser: {parser_name}")
    return parser_fn


async def ingest_file(
    session: AsyncSession,
    file_path: Path,
    match: MatchResult,
) -> IndexedFile | None:
    """Parse a file and upsert its data into the database.

    Returns the IndexedFile record, or None if the file hasn't changed.
    """
    file_hash = hash_file(file_path)
    stat = file_path.stat()

    # Check if already indexed with same hash
    existing = await session.execute(
        select(IndexedFile).where(IndexedFile.file_path == str(file_path))
    )
    existing_file = existing.scalar_one_or_none()

    if existing_file and existing_file.file_hash == file_hash:
        logger.debug("Unchanged: %s", file_path.name)
        return None

    # Parse the file
    try:
        parser_fn = _resolve_parser(match, file_path)
        result: ParseResult = parser_fn(file_path, extract=match.extract)
    except Exception as e:
        logger.error("Parse error %s: %s", file_path.name, e)
        if existing_file:
            existing_file.status = "error"
            existing_file.error_msg = str(e)
        else:
            indexed = IndexedFile(
                file_path=str(file_path),
                file_hash=file_hash,
                format=file_path.suffix.lstrip("."),
                status="error",
                error_msg=str(e),
                file_size=stat.st_size,
                file_mtime=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            )
            session.add(indexed)
        await session.commit()
        return None

    # Upsert IndexedFile
    if existing_file:
        # Delete old sequences (cascades to features/primers)
        await session.execute(
            delete(Sequence).where(Sequence.file_id == existing_file.id)
        )
        existing_file.file_hash = file_hash
        existing_file.format = file_path.suffix.lstrip(".")
        existing_file.status = "active"
        existing_file.error_msg = None
        existing_file.file_size = stat.st_size
        existing_file.file_mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
        indexed = existing_file
    else:
        indexed = IndexedFile(
            file_path=str(file_path),
            file_hash=file_hash,
            format=file_path.suffix.lstrip("."),
            status="active",
            file_size=stat.st_size,
            file_mtime=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
        )
        session.add(indexed)
        await session.flush()  # Get indexed.id

    # Insert Sequence
    seq = Sequence(
        file_id=indexed.id,
        name=result.name,
        size_bp=result.size_bp,
        topology=result.topology,
        sequence=result.sequence,
        description=result.description,
        meta=result.meta or None,
    )
    session.add(seq)
    await session.flush()  # Get seq.id

    # Insert Features
    for f in result.features:
        session.add(Feature(
            seq_id=seq.id,
            name=f.name,
            type=f.type,
            start=f.start,
            end=f.end,
            strand=f.strand,
            qualifiers=f.qualifiers or None,
        ))

    # Insert Primers
    for p in result.primers:
        session.add(Primer(
            seq_id=seq.id,
            name=p.name,
            sequence=p.sequence,
            tm=p.tm,
            start=p.start,
            end=p.end,
            strand=p.strand,
        ))

    await session.commit()
    logger.info(
        "Indexed: %s (%d bp, %d features, %d primers)",
        result.name, result.size_bp, len(result.features), len(result.primers),
    )
    return indexed


async def remove_file(session: AsyncSession, file_path: Path) -> bool:
    """Mark a file as deleted and remove its sequences."""
    result = await session.execute(
        select(IndexedFile).where(IndexedFile.file_path == str(file_path))
    )
    indexed = result.scalar_one_or_none()

    if not indexed:
        return False

    # Cascade delete removes sequences, features, primers
    await session.execute(
        delete(Sequence).where(Sequence.file_id == indexed.id)
    )
    indexed.status = "deleted"
    await session.commit()
    logger.info("Removed: %s", file_path.name)
    return True
