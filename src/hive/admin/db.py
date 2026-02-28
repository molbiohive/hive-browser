"""Database audit and cleanup operations — audit, dedupe, prune."""

import hashlib
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hive.db.models import Feature, IndexedFile, Primer, Sequence

logger = logging.getLogger(__name__)


async def audit(
    session: AsyncSession,
    watcher_root: str,
    verbose: bool = False,
) -> dict:
    """Audit database integrity — counts, duplicates, orphans.

    Returns a structured dict with totals, duplicate groups, and orphan files.
    """
    root = Path(watcher_root).expanduser().resolve()

    # --- Totals ---
    active_files = (await session.execute(
        select(func.count()).select_from(IndexedFile)
        .where(IndexedFile.status == "active")
    )).scalar()
    error_files = (await session.execute(
        select(func.count()).select_from(IndexedFile)
        .where(IndexedFile.status == "error")
    )).scalar()
    deleted_files = (await session.execute(
        select(func.count()).select_from(IndexedFile)
        .where(IndexedFile.status == "deleted")
    )).scalar()
    sequences = (await session.execute(
        select(func.count()).select_from(Sequence)
    )).scalar()
    features = (await session.execute(
        select(func.count()).select_from(Feature)
    )).scalar()
    primers = (await session.execute(
        select(func.count()).select_from(Primer)
    )).scalar()

    # --- Hash duplicates (active files with same file_hash) ---
    dupe_q = (
        select(IndexedFile.file_hash, func.count().label("cnt"))
        .where(IndexedFile.status == "active")
        .group_by(IndexedFile.file_hash)
        .having(func.count() > 1)
    )
    dupe_rows = (await session.execute(dupe_q)).all()
    hash_dupe_groups = len(dupe_rows)
    hash_dupe_files = sum(r.cnt for r in dupe_rows)

    hash_dupe_details = []
    if verbose and dupe_rows:
        for row in dupe_rows:
            paths_q = (
                select(IndexedFile.id, IndexedFile.file_path)
                .where(IndexedFile.status == "active", IndexedFile.file_hash == row.file_hash)
                .order_by(IndexedFile.id)
            )
            paths = (await session.execute(paths_q)).all()
            hash_dupe_details.append({
                "hash": row.file_hash[:12],
                "count": row.cnt,
                "files": [{"id": p.id, "path": p.file_path} for p in paths],
            })

    # --- Inode duplicates (symlinks/hardlinks to same physical file) ---
    active_q = select(IndexedFile.id, IndexedFile.file_path).where(
        IndexedFile.status == "active"
    )
    active_rows = (await session.execute(active_q)).all()

    inode_map: dict[tuple[int, int], list[dict]] = {}
    for row in active_rows:
        try:
            st = os.stat(row.file_path)
            key = (st.st_dev, st.st_ino)
            inode_map.setdefault(key, []).append({"id": row.id, "path": row.file_path})
        except OSError:
            pass  # orphans handled separately

    inode_dupe_groups = sum(1 for v in inode_map.values() if len(v) > 1)
    inode_dupe_files = sum(len(v) for v in inode_map.values() if len(v) > 1)

    inode_dupe_details = []
    if verbose:
        for entries in inode_map.values():
            if len(entries) > 1:
                inode_dupe_details.append({"count": len(entries), "files": entries})

    # --- Orphans (active files where path no longer exists) ---
    orphan_count = 0
    orphan_details = []
    for row in active_rows:
        if not Path(row.file_path).exists():
            orphan_count += 1
            if verbose:
                orphan_details.append({"id": row.id, "path": row.file_path})

    result = {
        "totals": {
            "indexed_files": {
                "active": active_files, "error": error_files, "deleted": deleted_files,
            },
            "sequences": sequences,
            "features": features,
            "primers": primers,
        },
        "hash_duplicates": {"groups": hash_dupe_groups, "files": hash_dupe_files},
        "inode_duplicates": {"groups": inode_dupe_groups, "files": inode_dupe_files},
        "orphans": orphan_count,
        "watcher_root": str(root),
    }

    if verbose:
        result["hash_duplicate_details"] = hash_dupe_details
        result["inode_duplicate_details"] = inode_dupe_details
        result["orphan_details"] = orphan_details

    return result


async def dedupe(session: AsyncSession, dry_run: bool = True) -> dict:
    """Remove duplicate IndexedFile records (same file_hash).

    Keeps the newest record (highest id), deletes older ones.
    Returns dict with removed count and details.
    """
    dupe_q = (
        select(IndexedFile.file_hash)
        .where(IndexedFile.status == "active")
        .group_by(IndexedFile.file_hash)
        .having(func.count() > 1)
    )
    dupe_hashes = (await session.execute(dupe_q)).scalars().all()

    to_remove = []
    for file_hash in dupe_hashes:
        rows = (await session.execute(
            select(IndexedFile)
            .where(IndexedFile.status == "active", IndexedFile.file_hash == file_hash)
            .order_by(IndexedFile.id.desc())
        )).scalars().all()

        # Keep newest (first), remove rest
        for old in rows[1:]:
            to_remove.append({"id": old.id, "path": old.file_path, "hash": old.file_hash[:12]})

    if not dry_run and to_remove:
        from sqlalchemy import delete
        ids = [r["id"] for r in to_remove]
        for file_id in ids:
            await session.execute(delete(Sequence).where(Sequence.file_id == file_id))
            await session.execute(delete(IndexedFile).where(IndexedFile.id == file_id))
        await session.commit()

    return {
        "dry_run": dry_run,
        "removed": len(to_remove),
        "details": to_remove,
    }


def _sequence_hash(seq_text: str) -> str:
    """SHA256 of sequence string (lightweight fingerprint)."""
    return hashlib.sha256(seq_text.encode()).hexdigest()


async def prune(
    session: AsyncSession,
    watcher_root: str,
    archive_dir: str | None = None,
    dry_run: bool = True,
    no_archive: bool = False,
) -> dict:
    """Remove IndexedFile records whose files no longer exist on disk.

    Optionally archives record data to JSONL before deletion.
    """
    active_q = select(IndexedFile).where(IndexedFile.status == "active")
    active_rows = (await session.execute(active_q)).scalars().all()

    orphans = []
    for f in active_rows:
        if not Path(f.file_path).exists():
            orphans.append(f)

    details = [{"id": f.id, "path": f.file_path} for f in orphans]

    if dry_run or not orphans:
        return {"dry_run": dry_run, "pruned": len(orphans), "details": details}

    # Archive before deleting
    if not no_archive and archive_dir:
        archive_path = Path(archive_dir)
        archive_path.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        jsonl_path = archive_path / f"prune-{ts}.jsonl"

        with open(jsonl_path, "w") as fh:
            for f in orphans:
                seqs_q = select(Sequence).where(Sequence.file_id == f.id)
                seqs = (await session.execute(seqs_q)).scalars().all()

                for seq in seqs:
                    feats_q = select(Feature).where(Feature.seq_id == seq.id)
                    feats = (await session.execute(feats_q)).scalars().all()
                    primers_q = select(Primer).where(Primer.seq_id == seq.id)
                    primers_list = (await session.execute(primers_q)).scalars().all()

                    record = {
                        "file_path": f.file_path,
                        "file_hash": f.file_hash,
                        "format": f.format,
                        "name": seq.name,
                        "size_bp": seq.size_bp,
                        "sequence_hash": _sequence_hash(seq.sequence) if seq.sequence else None,
                        "topology": seq.topology,
                        "description": seq.description,
                        "meta": seq.meta,
                        "features": [
                            {"name": ft.name, "type": ft.type, "start": ft.start,
                             "end": ft.end, "strand": ft.strand}
                            for ft in feats
                        ],
                        "primers": [
                            {"name": p.name, "sequence": p.sequence, "tm": p.tm,
                             "start": p.start, "end": p.end, "strand": p.strand}
                            for p in primers_list
                        ],
                    }
                    fh.write(json.dumps(record) + "\n")

        logger.info("Archived %d orphan records to %s", len(orphans), jsonl_path)

    # Delete orphan records
    from sqlalchemy import delete
    for f in orphans:
        await session.execute(delete(Sequence).where(Sequence.file_id == f.id))
        await session.execute(delete(IndexedFile).where(IndexedFile.id == f.id))
    await session.commit()

    return {"dry_run": False, "pruned": len(orphans), "details": details}
