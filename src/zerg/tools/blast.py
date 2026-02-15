"""BLAST tool — sequence similarity search using local BLAST+."""

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from zerg.db import session as db
from zerg.db.models import IndexedFile, Sequence
from zerg.tools.base import Tool, ToolInput

logger = logging.getLogger(__name__)


class BlastInput(ToolInput):
    sequence: str = Field(
        ...,
        description="Query nucleotide sequence or sequence name to look up from DB",
    )
    evalue: float = Field(default=1e-5, description="E-value threshold")
    max_hits: int = Field(default=20, ge=1, le=100)


class BlastHit(BaseModel):
    subject: str
    identity: float
    alignment_length: int
    mismatches: int
    gaps: int
    q_start: int
    q_end: int
    s_start: int
    s_end: int
    evalue: float
    bitscore: float


class BlastTool(Tool):
    name = "blast"
    description = (
        "Find similar sequences using BLAST+ alignment. "
        "Accepts raw nucleotide sequence or a sequence name from the database."
    )

    def __init__(self, db_path: str, binary: str = "blastn"):
        self._db_path = Path(db_path).expanduser()
        self._binary = binary

    def input_schema(self) -> type[ToolInput]:
        return BlastInput

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """Run BLAST+ against the local index."""
        inp = BlastInput(**params)
        query_seq = inp.sequence.strip()

        # If it looks like a name (no ATGC-only), resolve from DB
        if not _is_sequence(query_seq):
            resolved = await _resolve_sequence(query_seq)
            if resolved is None:
                return {"error": f"Sequence not found: {query_seq}", "hits": []}
            query_seq = resolved

        db_file = self._db_path / "zerg_blast"
        if not (self._db_path / "zerg_blast.ndb").exists():
            return {"error": "BLAST index not built yet", "hits": []}

        # Write query to temp FASTA
        with tempfile.NamedTemporaryFile(mode="w", suffix=".fasta", delete=False) as f:
            f.write(f">query\n{query_seq}\n")
            query_file = f.name

        try:
            proc = await asyncio.create_subprocess_exec(
                self._binary,
                "-query", query_file,
                "-db", str(db_file),
                "-outfmt", "6 sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore",
                "-evalue", str(inp.evalue),
                "-max_target_seqs", str(inp.max_hits),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
        finally:
            Path(query_file).unlink(missing_ok=True)

        if proc.returncode != 0:
            err = stderr.decode().strip()
            logger.error("BLAST failed: %s", err)
            return {"error": f"BLAST error: {err}", "hits": []}

        hits = []
        for line in stdout.decode().strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 11:
                continue
            hits.append(
                BlastHit(
                    subject=parts[0],
                    identity=float(parts[1]),
                    alignment_length=int(parts[2]),
                    mismatches=int(parts[3]),
                    gaps=int(parts[4]),
                    q_start=int(parts[5]),
                    q_end=int(parts[6]),
                    s_start=int(parts[7]),
                    s_end=int(parts[8]),
                    evalue=float(parts[9]),
                    bitscore=float(parts[10]),
                ).model_dump()
            )

        return {
            "hits": hits,
            "total": len(hits),
            "query_length": len(query_seq),
        }


def _is_sequence(s: str) -> bool:
    """Check if string looks like a nucleotide sequence."""
    clean = s.upper().replace(" ", "").replace("\n", "")
    if len(clean) < 10:
        return False
    valid = set("ATGCNRYSWKMBDHV")
    return all(c in valid for c in clean)


async def _resolve_sequence(name: str) -> str | None:
    """Look up a sequence by name in the database."""
    if not db.async_session_factory:
        return None
    async with db.async_session_factory() as session:
        row = (await session.execute(
            select(Sequence.sequence)
            .join(IndexedFile, Sequence.file_id == IndexedFile.id)
            .where(IndexedFile.status == "active")
            .where(Sequence.name.ilike(f"%{name}%"))
            .limit(1)
        )).scalar_one_or_none()
        return row


async def build_blast_index(db_path: str) -> bool:
    """Build BLAST database from all active sequences in the DB.

    Called on startup and after watcher changes.
    """
    if not db.async_session_factory:
        logger.warning("Cannot build BLAST index: database unavailable")
        return False

    blast_dir = Path(db_path).expanduser()
    blast_dir.mkdir(parents=True, exist_ok=True)
    fasta_file = blast_dir / "all_sequences.fasta"
    db_file = blast_dir / "zerg_blast"

    async with db.async_session_factory() as session:
        rows = (await session.execute(
            select(Sequence.name, Sequence.sequence)
            .join(IndexedFile, Sequence.file_id == IndexedFile.id)
            .where(IndexedFile.status == "active")
        )).all()

    if not rows:
        logger.info("No sequences to index for BLAST")
        return False

    # Write combined FASTA
    with open(fasta_file, "w") as f:
        for name, seq in rows:
            f.write(f">{name}\n{seq}\n")

    # Run makeblastdb
    proc = await asyncio.create_subprocess_exec(
        "makeblastdb",
        "-in", str(fasta_file),
        "-dbtype", "nucl",
        "-out", str(db_file),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        logger.error("makeblastdb failed: %s", stderr.decode())
        return False

    logger.info("BLAST index built: %d sequences", len(rows))
    return True
