"""BLAST-based variant detection -- find sequence-similar parts."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import delete, select

from hive.config import Settings
from hive.db import session as db
from hive.db.models import Annotation, Part, PartName
from hive.ps.base import Process, ProcessContext

if TYPE_CHECKING:
    from hive.deps import DepRegistry
    from hive.deps.blast import BlastDep

logger = logging.getLogger(__name__)


def _parse_part_id(subject: str) -> int | None:
    """Extract part ID from a pid_N_name subject string."""
    if not subject.startswith("pid_"):
        return None
    parts = subject.split("_", 2)
    if len(parts) < 2:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


def _process_hits(
    query_pid: int,
    query_length: int,
    hits: list[dict],
    min_identity: float,
    min_coverage: float,
) -> list[dict]:
    """Filter BLAST hits and return annotations to write.

    Returns list of {"pid": int, "identity": float, "coverage": float}.
    """
    results = []
    for hit in hits:
        hit_pid = _parse_part_id(hit["subject"])
        if hit_pid is None:
            continue  # skip non-part hits (sid_ entries)
        if hit_pid == query_pid:
            continue  # skip self

        identity = hit["identity"]
        coverage = (hit["alignment_length"] / query_length * 100) if query_length else 0
        if identity < min_identity or coverage < min_coverage:
            continue

        results.append({
            "pid": hit_pid,
            "identity": round(identity, 1),
            "coverage": round(coverage, 1),
        })
    return results


class MatchProcess(Process):
    """BLAST every part against the DB and flag sequence-similar pairs."""

    name = "match"
    description = "BLAST-based variant detection"

    def __init__(
        self,
        config: Settings,
        dep_registry: DepRegistry | None = None,
        *,
        min_identity: float = 90.0,
        min_coverage: float = 80.0,
    ):
        self._config = config
        self._dep_registry = dep_registry
        self._min_identity = min_identity
        self._min_coverage = min_coverage

    async def run(self, ctx: ProcessContext) -> str:
        if not self._dep_registry:
            return "No dep registry available"

        blast_dep: BlastDep | None = self._dep_registry.get("blast")  # type: ignore[assignment]
        if not blast_dep:
            return "BLAST dep not registered"

        if not db.async_session_factory:
            return "Database unavailable"

        db_path = Path(self._config.dep_data_dir("blast"))

        logger.info("Starting BLAST variant detection (identity>=%.0f%%, coverage>=%.0f%%)",
                    self._min_identity, self._min_coverage)

        # Clear previous blast annotations
        async with db.async_session_factory() as session:
            result = await session.execute(
                delete(Annotation).where(Annotation.source == "blast")
            )
            await session.commit()
            if result.rowcount:
                logger.info("Cleared %d previous blast annotations", result.rowcount)

        # Paginate parts
        batch_size = 50
        last_id = 0
        scanned = 0
        variants_found = 0

        while True:
            async with db.async_session_factory() as session:
                rows = (await session.execute(
                    select(Part.id, Part.sequence, Part.molecule)
                    .where(Part.id > last_id)
                    .order_by(Part.id)
                    .limit(batch_size)
                )).all()

            if not rows:
                break

            for pid, sequence, molecule in rows:
                last_id = pid

                # Pick program and prep sequence
                if molecule == "AA":
                    program = "blastp"
                    query_seq = sequence
                else:
                    program = "blastn"
                    query_seq = sequence.replace("U", "T").replace("u", "t")

                result = await blast_dep.run_search(
                    program, query_seq, db_path,
                )
                if result.get("error"):
                    logger.warning("BLAST error for pid %d: %s", pid, result["error"])
                    continue

                matches = _process_hits(
                    pid, len(sequence), result.get("hits", []),
                    self._min_identity, self._min_coverage,
                )

                if matches:
                    async with db.async_session_factory() as session:
                        for m in matches:
                            value = f"pid:{m['pid']} identity:{m['identity']} coverage:{m['coverage']}"
                            session.add(Annotation(
                                part_id=pid,
                                key="blast_similar",
                                value=value,
                                source="blast",
                            ))
                        await session.commit()
                    variants_found += len(matches)

                scanned += 1

            logger.info("Match progress: %d parts scanned, %d variants so far", scanned, variants_found)
            await ctx.check()

        logger.info("Match complete: %d parts scanned, %d variants found", scanned, variants_found)
        return f"{scanned} parts scanned, {variants_found} variants found"
