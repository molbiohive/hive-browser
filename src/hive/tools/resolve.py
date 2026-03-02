"""Shared resolvers -- sequence by SID/name, part by PID."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from hive.db.models import (
    Annotation,
    IndexedFile,
    Library,
    LibraryMember,
    Part,
    PartInstance,
    PartName,
    Sequence,
)


async def resolve_sequence(
    session: AsyncSession,
    *,
    sid: int | None = None,
    name: str | None = None,
    load_parts: bool = False,
    load_file: bool = False,
) -> Sequence | None:
    """Resolve a sequence by SID (primary) or exact name (fallback).

    Only returns sequences from active (non-deleted) indexed files.
    """
    stmt = (
        select(Sequence)
        .join(IndexedFile, Sequence.file_id == IndexedFile.id)
        .where(IndexedFile.status == "active")
    )

    if sid is not None:
        stmt = stmt.where(Sequence.id == sid)
    elif name:
        stmt = stmt.where(func.lower(Sequence.name) == func.lower(name))
    else:
        return None

    if load_parts:
        stmt = stmt.options(
            selectinload(Sequence.part_instances)
            .selectinload(PartInstance.part)
            .selectinload(Part.names)
        )
    if load_file:
        stmt = stmt.options(selectinload(Sequence.file))

    return (await session.execute(stmt.order_by(Sequence.id).limit(1))).scalar_one_or_none()


async def resolve_part(
    session: AsyncSession,
    *,
    pid: int,
    load_names: bool = False,
    load_instances: bool = False,
    load_annotations: bool = False,
    load_libraries: bool = False,
) -> Part | None:
    """Resolve a Part by PID with optional eager loading.

    Instances chain: Part.instances -> PartInstance.sequence -> Sequence.file.
    Libraries chain: Part.library_members -> LibraryMember.library.
    """
    stmt = select(Part).where(Part.id == pid)

    if load_names:
        stmt = stmt.options(selectinload(Part.names))
    if load_instances:
        stmt = stmt.options(
            selectinload(Part.instances)
            .selectinload(PartInstance.sequence)
            .selectinload(Sequence.file)
        )
    if load_annotations:
        stmt = stmt.options(selectinload(Part.annotations))
    if load_libraries:
        stmt = stmt.options(
            selectinload(Part.library_members)
            .selectinload(LibraryMember.library)
        )

    return (await session.execute(stmt)).scalar_one_or_none()


async def resolve_input(session: AsyncSession, raw: str) -> tuple[str, dict]:
    """Resolve raw sequence, sid:N, or pid:N to (sequence, metadata).

    Returns: (sequence_string, {"source": "raw"|"sid"|"pid", ...})
    Raises: ValueError if SID/PID not found.
    """
    raw = raw.strip()
    low = raw.lower()
    if low.startswith("sid:"):
        sid = int(raw[4:].strip())
        seq = await resolve_sequence(session, sid=sid)
        if not seq:
            raise ValueError(f"Sequence not found: SID {sid}")
        return seq.sequence, {"source": "sid", "sid": seq.id, "name": seq.name}
    if low.startswith("pid:"):
        pid = int(raw[4:].strip())
        part = await resolve_part(session, pid=pid, load_names=True)
        if not part:
            raise ValueError(f"Part not found: PID {pid}")
        return part.sequence, {
            "source": "pid",
            "pid": part.id,
            "names": [n.name for n in part.names],
        }
    return raw, {"source": "raw"}
