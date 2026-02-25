"""BLAST tool — sequence similarity search using local BLAST+."""

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


class BlastInput(BaseModel):
    sequence: str = Field(
        ...,
        description="Query nucleotide sequence or sequence name to look up from DB",
    )
    evalue: float = Field(default=1e-5, description="E-value threshold")


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
        return f"Found {total} BLAST hit(s)." if total else "No BLAST hits found."

    async def execute(self, params: dict[str, Any], mode: str = "direct") -> dict[str, Any]:
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

        # Dynamic sensitivity for short queries (blastn only)
        evalue = inp.evalue
        qlen = len(query_seq)
        search_params: dict[str, Any] = {"evalue": evalue}

        if evalue == 1e-5:
            if qlen < 20:
                search_params["evalue"] = 1000
            elif qlen < 50:
                search_params["evalue"] = 10

        if qlen < 30:
            search_params.update(task="blastn-short", word_size=7, dust="no")

        search_params["max_target_seqs"] = self._default_max_hits

        result = await run_search(
            "blastn", query_seq, self._db_path, bin_dir=self._bin_dir,
            **search_params,
        )

        if result.get("error"):
            return {"error": result["error"], "hits": []}

        hits = result["hits"]
        subject_names = result.get("subject_names", set())

        # Resolve file paths for hit subjects
        if hits:
            path_map = await _resolve_file_paths(subject_names)
            for hit in hits:
                hit["file_path"] = path_map.get(hit["subject"])

        return {
            "hits": hits,
            "total": len(hits),
            "query_length": result.get("query_length", qlen),
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
            result[safe_name] = display_file_path(file_path)
    return result


async def _resolve_sequence(name: str) -> str | None:
    """Look up a sequence by exact name in the database."""
    if not db.async_session_factory:
        return None
    from hive.tools.resolve import resolve_sequence as _resolve

    async with db.async_session_factory() as session:
        seq = await _resolve(session, name=name)
        return seq.sequence if seq else None
