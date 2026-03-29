"""SeqLogo tool -- compute position weight matrix from aligned sequences."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from pydantic import BaseModel, Field, field_validator

from hive.db import session as db
from hive.tools.base import Tool
from hive.tools.resolve import resolve_part, resolve_sequence


class SeqLogoInput(BaseModel):
    sids: list[int] = Field(
        default_factory=list,
        description="Sequence IDs to include",
    )
    pids: list[int] = Field(
        default_factory=list,
        description="Part IDs to include",
    )

    @field_validator("sids", "pids", mode="before")
    @classmethod
    def _parse_string_list(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

    region_start: int | None = Field(
        default=None,
        description="Start position to extract (1-based, optional)",
    )
    region_end: int | None = Field(
        default=None,
        description="End position to extract (1-based, optional)",
    )


def _detect_alphabet(seqs: list[str]) -> str:
    sample = "".join(s[:100] for s in seqs).upper().replace("-", "")
    if any(c in sample for c in "DEFHIKLMPQRSVWY"):
        return "protein"
    if "U" in sample and "T" not in sample:
        return "rna"
    return "dna"


def _compute_pwm(seqs: list[str], alphabet: str) -> list[dict[str, float]]:
    if not seqs:
        return []
    length = min(len(s) for s in seqs)
    positions = []
    for i in range(length):
        col = [s[i].upper() for s in seqs if i < len(s) and s[i] != "-"]
        if not col:
            positions.append({})
            continue
        counts = Counter(col)
        total = sum(counts.values())
        positions.append({base: count / total for base, count in counts.items()})
    return positions


class SeqLogoTool(Tool):
    name = "seqlogo"
    description = ("sequence logo", "Compute sequence logo (position weight matrix) from multiple sequences.")
    tags = {"analysis"}
    advanced = {"region_start", "region_end"}

    def __init__(self, config=None, **_):
        self._dep = None
        if config:
            try:
                from hive.deps import MafftDep
                self._dep = MafftDep(config.deps.mafft.bin_dir)
            except Exception:
                pass

    def input_schema(self) -> dict:
        schema = SeqLogoInput.model_json_schema()
        schema.pop("title", None)
        return schema

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        inp = SeqLogoInput(**params)
        total = len(inp.sids) + len(inp.pids)

        if total < 2:
            return {"error": "Need at least 2 sequences (SIDs and/or PIDs)"}

        if not db.async_session_factory:
            return {"error": "Database unavailable"}

        sequences: list[tuple[str, str]] = []
        async with db.async_session_factory() as session:
            for sid in inp.sids:
                seq = await resolve_sequence(session, sid=sid)
                if not seq:
                    return {"error": f"Sequence not found for SID {sid}"}
                sequences.append((seq.name, seq.sequence))
            for pid in inp.pids:
                part = await resolve_part(session, pid=pid, load_names=True)
                if not part:
                    return {"error": f"Part not found for PID {pid}"}
                name = part.names[0].name if part.names else f"PID_{pid}"
                sequences.append((name, part.sequence))

        # Extract region if specified
        raw_seqs = [s for _, s in sequences]
        if inp.region_start or inp.region_end:
            start = (inp.region_start or 1) - 1
            end = inp.region_end or max(len(s) for s in raw_seqs)
            raw_seqs = [s[start:end] for s in raw_seqs]

        # Align if sequences differ in length and MAFFT is available
        if len(set(len(s) for s in raw_seqs)) > 1:
            if not self._dep:
                return {"error": "Sequences differ in length and MAFFT is not configured for alignment"}
            pairs = [(n, s) for (n, _), s in zip(sequences, raw_seqs)]
            result = await self._dep.align(pairs)
            if result.get("error"):
                return result
            # Parse aligned FASTA
            aligned = []
            current = ""
            for line in result["aligned"].split("\n"):
                if line.startswith(">"):
                    if current:
                        aligned.append(current)
                    current = ""
                else:
                    current += line.strip()
            if current:
                aligned.append(current)
            raw_seqs = aligned

        alphabet = _detect_alphabet(raw_seqs)
        positions = _compute_pwm(raw_seqs, alphabet)

        return {
            "logo_positions": positions,
            "alphabet": alphabet,
            "sequence_count": len(raw_seqs),
            "logo_length": len(positions),
            "names": [n for n, _ in sequences],
        }
