"""Ingestion pipeline — parse file, upsert into database with Part-based identity."""

import hashlib
import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from hive.cloning.seq import reverse_complement
from hive.db.models import (
    CloningStep,
    IndexedFile,
    Part,
    PartInstance,
    PartName,
    Sequence,
)
from hive.libs import annotate_part
from hive.parsers import BIOPYTHON_PARSERS, PARSERS
from hive.parsers.base import ParseResult
from hive.utils import hash_sequence
from hive.watcher.rules import MatchResult


def build_search_text(result: ParseResult, tags: list[str] | None = None) -> str:
    """Build denormalized search text from parsed result for BM25 indexing."""
    parts = [result.name]
    if result.description:
        parts.append(result.description)
    for f in result.features:
        if f.name:
            parts.append(f.name)
    for p in result.primers:
        if p.name:
            parts.append(p.name)
    if tags:
        parts.extend(tags)
    meta = result.meta or {}
    if meta.get("history_keywords"):
        parts.append(meta["history_keywords"])
    return " ".join(parts)


def extract_tags(file_path: Path, watcher_root: str) -> list[str]:
    """Extract parent directory names relative to watcher root as tags."""
    try:
        rel = file_path.relative_to(Path(watcher_root).expanduser())
    except ValueError:
        return []
    return list(rel.parts[:-1])  # exclude filename


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


def _extract_subseq(
    parent_seq: str,
    start: int,
    end: int,
    strand: int,
    topology: str,
) -> str:
    """Extract subsequence from parent, handling circular wrap and reverse complement."""
    if start <= end:
        subseq = parent_seq[start:end]
    elif topology == "circular":
        subseq = parent_seq[start:] + parent_seq[:end]
    else:
        subseq = parent_seq[start:end]

    if strand == -1:
        subseq = reverse_complement(subseq)
    return subseq


async def get_or_create_part(
    session: AsyncSession,
    sequence: str,
    molecule: str,
) -> Part:
    """Find Part by sequence_hash or create new one."""
    seq_hash = hash_sequence(sequence)
    existing = await session.execute(select(Part).where(Part.sequence_hash == seq_hash))
    part = existing.scalar_one_or_none()
    if part:
        return part
    part = Part(
        sequence_hash=seq_hash,
        sequence=sequence.upper(),
        molecule=molecule,
        length=len(sequence),
    )
    session.add(part)
    await session.flush()
    return part


async def add_part_name(
    session: AsyncSession,
    part_id: int,
    name: str,
    source: str,
    source_detail: str | None = None,
):
    """Add a PartName if not already present for this (part, name, source)."""
    existing = await session.execute(
        select(PartName).where(
            PartName.part_id == part_id,
            PartName.name == name,
            PartName.source == source,
        )
    )
    if not existing.scalar_one_or_none():
        session.add(
            PartName(
                part_id=part_id,
                name=name,
                source=source,
                source_detail=source_detail,
            )
        )


async def ingest_file(
    session: AsyncSession,
    file_path: Path,
    match: MatchResult,
    commit: bool = True,
    watcher_root: str | None = None,
    force: bool = False,
) -> IndexedFile | None:
    """Parse a file and upsert its data into the database.

    Returns the IndexedFile record, or None if the file hasn't changed.
    """
    file_path = file_path.resolve()
    stat = file_path.stat()

    # Check if already indexed — fast mtime check before expensive hash
    existing = await session.execute(
        select(IndexedFile).where(IndexedFile.file_path == str(file_path))
    )
    existing_file = existing.scalar_one_or_none()

    if not force:
        if existing_file and existing_file.file_mtime:
            existing_ts = existing_file.file_mtime.timestamp()
            if abs(existing_ts - stat.st_mtime) < 1.0:
                logger.debug("Unchanged (mtime): %s", file_path.name)
                return None

        file_hash = hash_file(file_path)

        if existing_file and existing_file.file_hash == file_hash:
            logger.debug("Unchanged (hash): %s", file_path.name)
            return None
    else:
        file_hash = hash_file(file_path)

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

    # Merge directory tags into meta
    meta = dict(result.meta) if result.meta else {}
    if watcher_root:
        tags = extract_tags(file_path, watcher_root)
        if tags:
            meta["tags"] = tags

    # Upsert Sequence — update in-place to keep SID stable
    existing_seq = await session.execute(select(Sequence).where(Sequence.file_id == indexed.id))
    seq = existing_seq.scalar_one_or_none()

    search_text = build_search_text(result, meta.get("tags"))

    if seq:
        # Update fields in-place (SID stays the same)
        seq.name = result.name
        seq.length = result.size_bp
        seq.topology = result.topology
        seq.sequence = result.sequence
        seq.sequence_hash = hash_sequence(result.sequence)
        seq.molecule = result.molecule
        seq.description = result.description
        seq.search_text = search_text
        seq.meta = meta or None
        # Delete child rows that will be recreated below
        await session.execute(delete(PartInstance).where(PartInstance.seq_id == seq.id))
        await session.execute(delete(CloningStep).where(CloningStep.sequence_id == seq.id))
        await session.flush()
    else:
        seq = Sequence(
            file_id=indexed.id,
            name=result.name,
            length=result.size_bp,
            topology=result.topology,
            sequence=result.sequence,
            sequence_hash=hash_sequence(result.sequence),
            molecule=result.molecule,
            description=result.description,
            search_text=search_text,
            meta=meta or None,
        )
        session.add(seq)
        await session.flush()  # Get seq.id

    # For each ParsedFeature: extract subsequence, hash, get_or_create Part
    for f in result.features:
        subseq = _extract_subseq(
            result.sequence,
            f.start,
            f.end,
            f.strand,
            result.topology,
        )
        if not subseq:
            continue
        part = await get_or_create_part(session, subseq, result.molecule)
        await add_part_name(
            session,
            part.id,
            f.name,
            source="file",
            source_detail=file_path.name,
        )
        session.add(
            PartInstance(
                part_id=part.id,
                seq_id=seq.id,
                annotation_type=f.type,
                start=f.start,
                end=f.end,
                strand=f.strand,
                qualifiers=f.qualifiers or None,
            )
        )
        await annotate_part(session, part.id, f.type, subseq, result.molecule, name=f.name)

    # For each ParsedPrimer: create Part from oligo sequence
    for p in result.primers:
        if not p.sequence:
            continue
        part = await get_or_create_part(session, p.sequence, "DNA")
        await add_part_name(
            session,
            part.id,
            p.name,
            source="file",
            source_detail=file_path.name,
        )
        if p.start is not None and p.end is not None:
            session.add(
                PartInstance(
                    part_id=part.id,
                    seq_id=seq.id,
                    annotation_type="primer_bind",
                    start=p.start,
                    end=p.end,
                    strand=p.strand,
                )
            )
        await annotate_part(session, part.id, "primer_bind", p.sequence, "DNA", name=p.name)

    # Ingest cloning history steps
    history_steps = meta.get("history", [])
    if history_steps:
        # Insert steps, resolving parent_step_id via node_id mapping
        node_to_step: dict[int, int] = {}
        for step_data in history_steps:
            parent_node = step_data.get("parent_node_id")
            parent_step_id = node_to_step.get(parent_node) if parent_node is not None else None
            step = CloningStep(
                sequence_id=seq.id,
                node_id=step_data["node_id"],
                parent_step_id=parent_step_id,
                name=step_data.get("name", ""),
                operation=step_data.get("operation", "invalid"),
                seq_len=step_data.get("seq_len", 0),
                circular=step_data.get("circular", False),
                molecule_type=step_data.get("molecule_type", "DNA"),
                oligos=step_data.get("oligos", []),
                enzymes=step_data.get("enzymes", []),
                features=step_data.get("features", []),
                parameters=step_data.get("parameters", {}),
            )
            session.add(step)
            await session.flush()
            node_to_step[step_data["node_id"]] = step.id

            # Create Parts from history oligos (primers with their own sequences)
            for oligo in step_data.get("oligos", []):
                oligo_seq = oligo.get("sequence")
                if not oligo_seq:
                    continue
                part = await get_or_create_part(session, oligo_seq, "DNA")
                await add_part_name(
                    session,
                    part.id,
                    oligo.get("name", ""),
                    source="history",
                    source_detail=f"step:{step.id}",
                )
                await annotate_part(
                    session,
                    part.id,
                    "primer_bind",
                    oligo_seq,
                    "DNA",
                    name=oligo.get("name"),
                )

    if commit:
        await session.commit()

    n_parts = len(result.features) + len(result.primers)
    logger.info(
        "Indexed: %s (%d bp, %d features, %d primers, %d parts)",
        result.name,
        result.size_bp,
        len(result.features),
        len(result.primers),
        n_parts,
    )
    return indexed


async def remove_file(session: AsyncSession, file_path: Path) -> bool:
    """Mark a file as deleted and remove its sequences."""
    file_path = file_path.resolve()
    result = await session.execute(
        select(IndexedFile).where(IndexedFile.file_path == str(file_path))
    )
    indexed = result.scalar_one_or_none()

    if not indexed:
        return False

    # Cascade delete removes sequences and part_instances
    await session.execute(delete(Sequence).where(Sequence.file_id == indexed.id))
    indexed.status = "deleted"
    await session.commit()
    logger.info("Removed: %s", file_path.name)
    return True
