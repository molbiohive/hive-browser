"""Shared sequence resolver -- SID-first, exact name fallback."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from hive.db.models import IndexedFile, Sequence


async def resolve_sequence(
    session: AsyncSession,
    *,
    sid: int | None = None,
    name: str | None = None,
    load_features: bool = False,
    load_primers: bool = False,
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

    if load_features:
        stmt = stmt.options(selectinload(Sequence.features))
    if load_primers:
        stmt = stmt.options(selectinload(Sequence.primers))
    if load_file:
        stmt = stmt.options(selectinload(Sequence.file))

    return (await session.execute(stmt.order_by(Sequence.id).limit(1))).scalar_one_or_none()
