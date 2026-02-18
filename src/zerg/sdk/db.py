"""Read-only database access for external tools.

Injected into tools as self.db by the ToolFactory.
All methods return plain dicts — never exposes sessions or ORM models.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from zerg.db import session as db
from zerg.db.models import Feature, IndexedFile, Primer, Sequence

logger = logging.getLogger(__name__)


class ToolDB:
    """Read-only database access for external tools."""

    def _check_db(self) -> bool:
        if not db.async_session_factory:
            logger.warning("ToolDB: database unavailable")
            return False
        return True

    # --- Sequences ---

    async def find_sequences(
        self,
        query: str | None = None,
        topology: str | None = None,
        size_min: int | None = None,
        size_max: int | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search sequences by name (fuzzy) and optional filters.

        Returns: [{id, name, size_bp, topology, description, file_path}]
        """
        if not self._check_db():
            return []

        async with db.async_session_factory() as session:
            stmt = (
                select(
                    Sequence.id, Sequence.name, Sequence.size_bp,
                    Sequence.topology, Sequence.description,
                    IndexedFile.file_path,
                )
                .join(IndexedFile, Sequence.file_id == IndexedFile.id)
                .where(IndexedFile.status == "active")
            )

            if query:
                sim = func.similarity(Sequence.name, query)
                stmt = stmt.add_columns(sim.label("score"))
                stmt = stmt.where(sim > 0.1).order_by(sim.desc())
            else:
                stmt = stmt.add_columns(func.literal(1.0).label("score"))
                stmt = stmt.order_by(Sequence.name)

            if topology:
                stmt = stmt.where(Sequence.topology == topology)
            if size_min is not None:
                stmt = stmt.where(Sequence.size_bp >= size_min)
            if size_max is not None:
                stmt = stmt.where(Sequence.size_bp <= size_max)

            stmt = stmt.limit(limit)
            rows = (await session.execute(stmt)).all()

            return [
                {
                    "id": r.id, "name": r.name, "size_bp": r.size_bp,
                    "topology": r.topology, "description": r.description,
                    "file_path": r.file_path, "score": round(float(r.score), 3),
                }
                for r in rows
            ]

    async def get_sequence(
        self,
        id: int | None = None,
        name: str | None = None,
    ) -> dict[str, Any] | None:
        """Get one sequence with full details.

        Returns: {id, name, size_bp, topology, description, sequence, meta,
                  features: [...], primers: [...], file: {...}} or None.
        """
        if not self._check_db():
            return None
        if id is None and name is None:
            return None

        async with db.async_session_factory() as session:
            stmt = (
                select(Sequence)
                .join(IndexedFile, Sequence.file_id == IndexedFile.id)
                .options(
                    selectinload(Sequence.features),
                    selectinload(Sequence.primers),
                    selectinload(Sequence.file),
                )
                .where(IndexedFile.status == "active")
            )
            if id is not None:
                stmt = stmt.where(Sequence.id == id)
            else:
                stmt = stmt.where(Sequence.name.ilike(f"%{name}%"))

            seq = (await session.execute(stmt.limit(1))).scalar_one_or_none()
            if not seq:
                return None

            return {
                "id": seq.id,
                "name": seq.name,
                "size_bp": seq.size_bp,
                "topology": seq.topology,
                "description": seq.description,
                "sequence": seq.sequence,
                "meta": seq.meta,
                "features": [
                    {"id": f.id, "name": f.name, "type": f.type,
                     "start": f.start, "end": f.end, "strand": f.strand,
                     "qualifiers": f.qualifiers}
                    for f in seq.features
                ],
                "primers": [
                    {"id": p.id, "name": p.name, "sequence": p.sequence,
                     "tm": p.tm, "start": p.start, "end": p.end, "strand": p.strand}
                    for p in seq.primers
                ],
                "file": {
                    "path": seq.file.file_path,
                    "format": seq.file.format,
                    "size": seq.file.file_size,
                    "indexed_at": seq.file.indexed_at.isoformat() if seq.file.indexed_at else None,
                },
            }

    # --- Features ---

    async def find_features(
        self,
        seq_id: int | None = None,
        name: str | None = None,
        type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query features.

        Returns: [{id, name, type, start, end, strand, qualifiers, seq_name}]
        """
        if not self._check_db():
            return []

        async with db.async_session_factory() as session:
            stmt = (
                select(Feature, Sequence.name.label("seq_name"))
                .join(Sequence, Feature.seq_id == Sequence.id)
                .join(IndexedFile, Sequence.file_id == IndexedFile.id)
                .where(IndexedFile.status == "active")
            )
            if seq_id is not None:
                stmt = stmt.where(Feature.seq_id == seq_id)
            if name:
                stmt = stmt.where(Feature.name.ilike(f"%{name}%"))
            if type:
                stmt = stmt.where(Feature.type == type)

            stmt = stmt.limit(limit)
            rows = (await session.execute(stmt)).all()

            return [
                {
                    "id": f.id, "name": f.name, "type": f.type,
                    "start": f.start, "end": f.end, "strand": f.strand,
                    "qualifiers": f.qualifiers, "seq_name": seq_name,
                }
                for f, seq_name in rows
            ]

    # --- Primers ---

    async def find_primers(
        self,
        seq_id: int | None = None,
        name: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query primers.

        Returns: [{id, name, sequence, tm, start, end, strand, seq_name}]
        """
        if not self._check_db():
            return []

        async with db.async_session_factory() as session:
            stmt = (
                select(Primer, Sequence.name.label("seq_name"))
                .join(Sequence, Primer.seq_id == Sequence.id)
                .join(IndexedFile, Sequence.file_id == IndexedFile.id)
                .where(IndexedFile.status == "active")
            )
            if seq_id is not None:
                stmt = stmt.where(Primer.seq_id == seq_id)
            if name:
                stmt = stmt.where(Primer.name.ilike(f"%{name}%"))

            stmt = stmt.limit(limit)
            rows = (await session.execute(stmt)).all()

            return [
                {
                    "id": p.id, "name": p.name, "sequence": p.sequence,
                    "tm": p.tm, "start": p.start, "end": p.end,
                    "strand": p.strand, "seq_name": seq_name,
                }
                for p, seq_name in rows
            ]

    # --- Files ---

    async def find_files(
        self,
        format: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List indexed files.

        Returns: [{id, file_path, format, file_size, indexed_at}]
        """
        if not self._check_db():
            return []

        async with db.async_session_factory() as session:
            stmt = (
                select(IndexedFile)
                .where(IndexedFile.status == "active")
                .order_by(IndexedFile.indexed_at.desc())
            )
            if format:
                stmt = stmt.where(IndexedFile.format == format)

            stmt = stmt.limit(limit)
            rows = (await session.execute(stmt)).scalars().all()

            return [
                {
                    "id": f.id, "file_path": f.file_path, "format": f.format,
                    "file_size": f.file_size,
                    "indexed_at": f.indexed_at.isoformat() if f.indexed_at else None,
                }
                for f in rows
            ]

    # --- Counts ---

    async def count(self, table: str = "sequences") -> int:
        """Count rows in a table.

        Args:
            table: 'sequences' | 'features' | 'primers' | 'files'
        """
        if not self._check_db():
            return 0

        model_map = {
            "sequences": Sequence,
            "features": Feature,
            "primers": Primer,
            "files": IndexedFile,
        }
        model = model_map.get(table)
        if not model:
            return 0

        async with db.async_session_factory() as session:
            stmt = select(func.count()).select_from(model)
            if model is IndexedFile:
                stmt = stmt.where(IndexedFile.status == "active")
            return (await session.execute(stmt)).scalar() or 0
