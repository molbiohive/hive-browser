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
from hive.deps.blast import BlastDep
from hive.tools.base import Tool
from hive.tools.resolve import resolve_input

logger = logging.getLogger(__name__)

VALID_PROGRAMS = {"blastn", "blastp", "blastx", "tblastn", "tblastx"}

# Valid nucleotide characters (IUPAC)
_NUCL_CHARS = set("ATGCNRYSWKMBDHV")
# Amino acid chars that distinguish protein from nucleotide
_PROT_ONLY = set("EFIJLOPQZX*")


class BlastInput(BaseModel):
    sequence: str = Field(
        ...,
        description=(
            "DNA/protein sequence, sid:N for Sequence ID,"
            " pid:N for Part ID, or bare integer for SID"
        ),
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
    # Strip sequence names from LLM summaries -- SID is sufficient
    redact_keys = Tool.redact_keys | {"subject"}
    guidelines = (
        "Sequence similarity search using BLAST+. Supports blastn "
        "(nucl vs nucl), blastp (prot vs prot), blastx (nucl query "
        "vs prot db), tblastn, tblastx. Set program='auto' to detect "
        "from sequence type. Use SID (integer from search results) or "
        "pid:N (Part ID) to search with a database sequence."
    )

    def __init__(self, config=None, **_):
        if not config:
            raise ValueError("BlastTool requires config")
        blast_dir = config.dep_data_dir("blast")
        self._db_path = Path(blast_dir)
        self._dep = BlastDep(blast_dir, config.deps.blast.bin_dir)
        self._default_evalue = config.deps.blast.default_evalue
        self._default_max_hits = config.deps.blast.default_max_hits

    def input_schema(self) -> dict:
        schema = BlastInput.model_json_schema()
        schema.pop("title", None)
        return schema

    def llm_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "sequence": {
                    "type": "string",
                    "description": "DNA/protein sequence, sid:N, pid:N, or bare integer SID",
                },
            },
            "required": ["sequence"],
        }

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

        # Resolve sid:N, pid:N, bare integer SID, or name fallback
        low = query_seq.lower()
        if low.startswith(("sid:", "pid:")) or query_seq.isdigit():
            # Normalise bare integer to sid:N for resolve_input
            raw = f"sid:{query_seq}" if query_seq.isdigit() else query_seq
            if not db.async_session_factory:
                return {"error": "Database unavailable", "hits": []}
            async with db.async_session_factory() as session:
                try:
                    query_seq, _meta = await resolve_input(session, raw)
                except ValueError as exc:
                    return {"error": str(exc), "hits": []}
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

        result = await self._dep.run_search(
            program, query_seq, self._db_path,
            **search_params,
        )

        if result.get("error"):
            return {"error": result["error"], "hits": [], "program": program}

        hits = result["hits"]
        subject_names = result.get("subject_names", set())

        if hits:
            meta_map = await _resolve_hit_metadata(subject_names)
            for hit in hits:
                meta = meta_map.get(hit["subject"], {})
                hit["sid"] = meta.get("sid")
                hit["pid"] = meta.get("pid")
                hit["file_path"] = meta.get("file_path")

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


async def _resolve_by_name(name: str) -> str | None:
    """Look up a sequence by exact name (legacy fallback)."""
    if not db.async_session_factory:
        return None
    from hive.tools.resolve import resolve_sequence

    async with db.async_session_factory() as session:
        seq = await resolve_sequence(session, name=name)
        return seq.sequence if seq else None


async def _resolve_hit_metadata(names: set[str]) -> dict[str, dict]:
    """Look up SID/PID and file path for hit subject names.

    Sequence hits have plain names. Part hits have 'pid_N_name' format.
    """
    if not db.async_session_factory or not names:
        return {}

    # Separate part hits (pid_N_*) from sequence hits
    part_names = {n for n in names if n.startswith("pid_")}
    seq_names = names - part_names

    result: dict[str, dict] = {}

    async with db.async_session_factory() as session:
        # Resolve sequence hits
        if seq_names:
            rows = (await session.execute(
                select(Sequence.id, Sequence.name, IndexedFile.file_path)
                .join(IndexedFile, Sequence.file_id == IndexedFile.id)
                .where(IndexedFile.status == "active")
            )).all()
            for sid, seq_name, file_path in rows:
                safe_name = seq_name.replace(" ", "_")
                if safe_name in seq_names:
                    result[safe_name] = {
                        "sid": sid,
                        "file_path": display_file_path(file_path),
                    }

    # Resolve part hits by parsing pid_N from subject name
    for pname in part_names:
        # Format: pid_N_name
        parts = pname.split("_", 2)
        if len(parts) >= 2:
            try:
                pid = int(parts[1])
                result[pname] = {"pid": pid}
            except ValueError:
                pass

    return result
