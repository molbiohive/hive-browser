"""BLAST tool — sequence similarity search using local BLAST+."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from zerg.db import session as db
from zerg.db.models import IndexedFile, Sequence
from zerg.tools.base import Tool

logger = logging.getLogger(__name__)


class BlastInput(BaseModel):
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
    widget = "blast"
    tags = {"llm", "search"}
    guidelines = "BLAST similarity search. Accepts nucleotide sequence or DB name."

    def __init__(self, config=None, **_):
        if not config:
            raise ValueError("BlastTool requires config")
        self._db_path = Path(config.blast_dir)
        self._binary = config.blast.binary

    def input_schema(self) -> dict:
        schema = BlastInput.model_json_schema()
        schema.pop("title", None)
        return schema

    def format_result(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        total = len(result.get("hits", []))
        return f"Found {total} BLAST hit(s)." if total else "No BLAST hits found."

    def summary_for_llm(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        hits = result.get("hits", [])
        if not hits:
            return "No BLAST hits found."
        parts = [f"{h['subject']} ({h['identity']:.1f}%)" for h in hits]
        return f"Found {len(hits)} BLAST hit(s): {', '.join(parts)}."

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """Run BLAST+ against the local index."""
        if not params.get("sequence"):
            return {
                "error": "Missing required parameter: sequence "
                "(nucleotide sequence or name)",
                "hits": [],
            }

        # Strip None values so Pydantic defaults apply
        cleaned = {k: v for k, v in params.items() if v is not None}
        inp = BlastInput(**cleaned)
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

        # Dynamic sensitivity for short queries
        qlen = len(query_seq)
        evalue = inp.evalue
        if evalue == 1e-5:  # user didn't override default
            if qlen < 20:
                evalue = 1000
            elif qlen < 50:
                evalue = 10

        cmd = [
            self._binary,
            "-query", query_file,
            "-db", str(db_file),
            "-outfmt",
            "6 sseqid pident length mismatch gapopen "
            "qstart qend sstart send evalue bitscore",
            "-evalue", str(evalue),
            "-max_target_seqs", str(inp.max_hits),
        ]
        if qlen < 30:
            cmd.extend(["-task", "blastn-short", "-word_size", "7", "-dust", "no"])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
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
        subject_names = set()
        for line in stdout.decode().strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 11:
                continue
            subject_name = parts[0]
            subject_names.add(subject_name)
            hits.append(
                BlastHit(
                    subject=subject_name,
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

        # Resolve file paths for hit subjects
        if hits:
            path_map = await _resolve_file_paths(subject_names)
            for hit in hits:
                hit["file_path"] = path_map.get(hit["subject"])

        return {
            "hits": hits,
            "total": len(hits),
            "query_length": len(query_seq),
        }


def _is_sequence(s: str) -> bool:
    """Check if string looks like a nucleotide sequence (min 4 chars)."""
    clean = s.upper().replace(" ", "").replace("\n", "")
    if len(clean) < 4:
        return False
    valid = set("ATGCNRYSWKMBDHV")
    return all(c in valid for c in clean)


async def _resolve_file_paths(names: set[str]) -> dict[str, str]:
    """Look up file paths for sequence names (used to enable Open button on BLAST hits)."""
    if not db.async_session_factory or not names:
        return {}
    # BLAST index replaces spaces with underscores, so match both forms
    async with db.async_session_factory() as session:
        rows = (await session.execute(
            select(Sequence.name, IndexedFile.file_path)
            .join(IndexedFile, Sequence.file_id == IndexedFile.id)
            .where(IndexedFile.status == "active")
        )).all()
    result = {}
    for seq_name, file_path in rows:
        safe_name = seq_name.replace(" ", "_")
        if safe_name in names:
            result[safe_name] = file_path
    return result


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

    Called on startup and after watcher changes.  Uses a lockfile
    to prevent races when multiple workers start simultaneously.
    """
    if not db.async_session_factory:
        logger.warning("Cannot build BLAST index: database unavailable")
        return False

    blast_dir = Path(db_path).expanduser()
    blast_dir.mkdir(parents=True, exist_ok=True)
    fasta_file = blast_dir / "all_sequences.fasta"
    db_file = blast_dir / "zerg_blast"
    lock_file = blast_dir / ".build.lock"

    # Skip if another worker is already building
    try:
        fd = lock_file.open("x")  # atomic create — fails if exists
    except FileExistsError:
        logger.info("BLAST index build already in progress, skipping")
        return True
    try:
        return await _do_build_index(blast_dir, fasta_file, db_file)
    finally:
        fd.close()
        lock_file.unlink(missing_ok=True)


async def _do_build_index(blast_dir: Path, fasta_file: Path, db_file: Path) -> bool:
    # Remove stale index files before rebuilding
    for old in blast_dir.glob("zerg_blast.*"):
        old.unlink()

    async with db.async_session_factory() as session:
        rows = (await session.execute(
            select(Sequence.name, Sequence.sequence, Sequence.meta)
            .join(IndexedFile, Sequence.file_id == IndexedFile.id)
            .where(IndexedFile.status == "active")
        )).all()

    if not rows:
        logger.info("No sequences to index for BLAST")
        return False

    # Write combined FASTA — skip protein, convert RNA (U→T) for nucleotide DB
    written = 0
    with open(fasta_file, "w") as f:
        for name, seq, meta in rows:
            mol = (meta or {}).get("molecule_type", "DNA")
            if mol == "protein":
                continue
            safe_name = name.replace(" ", "_")
            nucl_seq = seq.replace("U", "T").replace("u", "t") if mol == "RNA" else seq
            f.write(f">{safe_name}\n{nucl_seq}\n")
            written += 1

    if not written:
        logger.info("No nucleotide sequences to index for BLAST")
        return False

    # Run makeblastdb
    proc = await asyncio.create_subprocess_exec(
        "makeblastdb",
        "-in", str(fasta_file),
        "-dbtype", "nucl",
        "-out", str(db_file),
        "-blastdb_version", "4",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        logger.error("makeblastdb failed: %s", stderr.decode())
        return False

    logger.info("BLAST index built: %d sequences (%d skipped)", written, len(rows) - written)
    return True
