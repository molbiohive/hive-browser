"""BLAST tool — sequence similarity search using all BLAST+ programs."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from hive.config import display_file_path
from hive.db import session as db
from hive.db.models import IndexedFile, Sequence
from hive.deps.blast import run_search
from hive.tools.base import Tool

logger = logging.getLogger(__name__)

VALID_PROGRAMS = {"blastn", "blastp", "blastx", "tblastn", "tblastx"}

# Valid nucleotide characters (IUPAC)
_NUCL_CHARS = set("ATGCNRYSWKMBDHV")
# Amino acid chars that distinguish protein from nucleotide
_PROT_ONLY = set("EFIJLOPQZX*")


class BlastInput(BaseModel):
    sequence: str = Field(
        ...,
        description="Query sequence or SID (integer) to look up from DB",
    )
    program: str = Field(
        default="auto",
        description=(
            "BLAST program: auto, blastn, blastp, blastx, tblastn, tblastx"
        ),
    )
    evalue: float | None = Field(
        default=None, description="E-value threshold",
    )
    max_hits: int | None = Field(
        default=None, description="Maximum number of hits to return",
    )
    word_size: int | None = Field(
        default=None, description="Word size for initial matches",
    )
    matrix: str | None = Field(
        default=None,
        description="Scoring matrix (protein: BLOSUM62, BLOSUM45, PAM250)",
    )
    gap_open: int | None = Field(
        default=None, description="Gap opening cost",
    )
    gap_extend: int | None = Field(
        default=None, description="Gap extension cost",
    )
    task: str | None = Field(
        default=None,
        description="Program subtask (e.g. blastn-short, megablast)",
    )
    extra: dict[str, str] = Field(
        default_factory=dict,
        description="Additional BLAST+ CLI flags as key-value pairs",
    )


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
        "Supports blastn, blastp, blastx, tblastn, tblastx."
    )
    widget = "blast"
    tags = {"llm", "search"}
    guidelines = (
        "Sequence similarity search using BLAST+. Supports blastn "
        "(nucl vs nucl), blastp (prot vs prot), blastx (nucl query "
        "vs prot db), tblastn, tblastx. Set program='auto' to detect "
        "from sequence type. Use SID (integer from search results) to "
        "search with a database sequence."
    )

    def __init__(self, config=None, **_):
        if not config:
            raise ValueError("BlastTool requires config")
        self._db_path = Path(config.blast_dir)
        self._bin_dir = config.blast.bin_dir
        self._default_evalue = config.blast.default_evalue
        self._default_max_hits = config.blast.default_max_hits

    def input_schema(self) -> dict:
        schema = BlastInput.model_json_schema()
        schema.pop("title", None)
        return schema

    def format_result(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        total = len(result.get("hits", []))
        prog = result.get("program", "blast")
        return (
            f"Found {total} {prog} hit(s)." if total
            else f"No {prog} hits found."
        )

    async def execute(
        self, params: dict[str, Any], mode: str = "direct",
    ) -> dict[str, Any]:
        """Run BLAST+ against the local index."""
        if not params.get("sequence"):
            return {
                "error": "Missing required parameter: sequence",
                "hits": [],
            }

        cleaned = {k: v for k, v in params.items() if v is not None}
        inp = BlastInput(**cleaned)
        query_seq = inp.sequence.strip()

        # Resolve SID (integer) from DB
        if query_seq.isdigit():
            resolved = await _resolve_by_sid(int(query_seq))
            if resolved is None:
                return {
                    "error": f"Sequence not found for SID {query_seq}",
                    "hits": [],
                }
            query_seq = resolved
        elif not _is_nucleotide(query_seq) and not _is_protein(query_seq):
            # Legacy: try name-based lookup
            resolved = await _resolve_by_name(query_seq)
            if resolved is None:
                return {
                    "error": f"Sequence not found: {query_seq}",
                    "hits": [],
                }
            query_seq = resolved

        # Auto-detect program
        program = inp.program.lower()
        if program == "auto":
            program = "blastp" if _is_protein(query_seq) else "blastn"
        if program not in VALID_PROGRAMS:
            return {
                "error": f"Invalid program: {program}. "
                f"Use: {', '.join(sorted(VALID_PROGRAMS))}",
                "hits": [],
            }

        # Build params from explicit fields
        search_params: dict[str, Any] = {}
        search_params["evalue"] = inp.evalue or self._default_evalue
        search_params["max_target_seqs"] = inp.max_hits or self._default_max_hits

        if inp.word_size is not None:
            search_params["word_size"] = inp.word_size
        if inp.matrix is not None:
            search_params["matrix"] = inp.matrix
        if inp.gap_open is not None:
            search_params["gapopen"] = inp.gap_open
        if inp.gap_extend is not None:
            search_params["gapextend"] = inp.gap_extend
        if inp.task is not None:
            search_params["task"] = inp.task

        # Merge extra flags
        search_params.update(inp.extra)

        # Dynamic sensitivity for short blastn queries
        if program == "blastn":
            qlen = len(query_seq)
            evalue = search_params["evalue"]
            if evalue == self._default_evalue:
                if qlen < 20:
                    search_params["evalue"] = 1000
                elif qlen < 50:
                    search_params["evalue"] = 10
            if qlen < 30 and "task" not in search_params:
                search_params["task"] = "blastn-short"
                search_params.setdefault("word_size", 7)
                search_params.setdefault("dust", "no")

        result = await run_search(
            program, query_seq, self._db_path,
            bin_dir=self._bin_dir, **search_params,
        )

        if result.get("error"):
            return {"error": result["error"], "hits": [], "program": program}

        hits = result["hits"]
        subject_names = result.get("subject_names", set())

        if hits:
            path_map = await _resolve_file_paths(subject_names)
            for hit in hits:
                hit["file_path"] = path_map.get(hit["subject"])

        return {
            "hits": hits,
            "total": len(hits),
            "query_length": result.get("query_length", len(query_seq)),
            "program": program,
        }


def _is_nucleotide(s: str) -> bool:
    """Check if string looks like a nucleotide sequence (min 4 chars)."""
    clean = s.upper().replace(" ", "").replace("\n", "")
    if len(clean) < 4:
        return False
    return all(c in _NUCL_CHARS for c in clean)


def _is_protein(s: str) -> bool:
    """Check if string looks like a protein sequence (min 4 chars)."""
    clean = s.upper().replace(" ", "").replace("\n", "")
    if len(clean) < 4:
        return False
    # If it contains any protein-only characters, it's protein
    # Otherwise ambiguous (e.g. "ACGT" valid as both) — default to nucl
    return any(c in _PROT_ONLY for c in clean)


async def _resolve_by_sid(sid: int) -> str | None:
    """Look up a sequence by SID."""
    if not db.async_session_factory:
        return None
    from hive.tools.resolve import resolve_sequence

    async with db.async_session_factory() as session:
        seq = await resolve_sequence(session, sid=sid)
        return seq.sequence if seq else None


async def _resolve_by_name(name: str) -> str | None:
    """Look up a sequence by exact name (legacy fallback)."""
    if not db.async_session_factory:
        return None
    from hive.tools.resolve import resolve_sequence

    async with db.async_session_factory() as session:
        seq = await resolve_sequence(session, name=name)
        return seq.sequence if seq else None


async def _resolve_file_paths(names: set[str]) -> dict[str, str]:
    """Look up file paths for hit subject names."""
    if not db.async_session_factory or not names:
        return {}
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
            result[safe_name] = display_file_path(file_path)
    return result
