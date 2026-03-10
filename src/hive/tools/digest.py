"""Digest tool — restriction enzyme digestion analysis."""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, Field

from hive.db import session as db
from hive.tools.base import Tool
from hive.tools.resolve import resolve_input


# NEB 1kb+ DNA Ladder — (size_bp, relative_intensity)
_1KB_PLUS_LADDER = [
    (10000, 0.4), (8000, 0.3), (6000, 0.3), (5000, 0.35),
    (4000, 0.35), (3000, 1.0), (2000, 0.4), (1500, 0.4),
    (1000, 1.0), (500, 0.5), (250, 0.3),
]


def _band_position(size: int, log_max: float, log_min: float) -> float:
    """Log-linear migration position, clamped to [0.05, 0.95]."""
    if size <= 0:
        return 0.95
    pos = (log_max - math.log10(size)) / (log_max - log_min)
    return max(0.05, min(0.95, pos))


def _compute_gel_data(fragments: list[int]) -> dict:
    """Build GelData for Hatchlings GelViewer."""
    log_max = math.log10(10000)
    log_min = math.log10(250)

    ladder_bands = [
        {
            "position": _band_position(size, log_max, log_min),
            "intensity": intensity,
            "size": size,
            "name": f"{size} bp",
        }
        for size, intensity in _1KB_PLUS_LADDER
    ]

    max_frag = max(fragments) if fragments else 1
    sample_bands = [
        {
            "position": _band_position(size, log_max, log_min),
            "intensity": max(0.3, min(1.0, size / max_frag)),
            "size": size,
            "name": f"{size} bp",
        }
        for size in sorted(fragments, reverse=True)
    ]

    return {
        "lanes": [
            {"label": "1kb+ Ladder", "bands": ladder_bands, "isLadder": True},
            {"label": "Sample", "bands": sample_bands},
        ],
        "gelType": "agarose",
        "stain": "ethidium",
    }


class DigestInput(BaseModel):
    sequence: str = Field(
        ...,
        description="DNA sequence, or sid:N for Sequence ID, or pid:N for Part ID",
    )
    enzymes: list[str] = Field(..., description='Enzyme names, e.g. ["EcoRI", "BamHI"]')
    circular: bool = Field(
        default=True,
        description="True for circular (plasmid), False for linear",
    )


class DigestTool(Tool):
    name = "digest"
    description = "Find restriction enzyme cut sites and calculate fragment sizes."
    widget = "digest"
    tags = {"llm", "analysis"}
    guidelines = "Restriction digest. Provide enzymes list and sequence (or sid:N / pid:N)."

    def __init__(self, **_):
        pass

    def input_schema(self) -> dict:
        schema = DigestInput.model_json_schema()
        schema.pop("title", None)
        return schema

    def llm_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "sequence": {"type": "string", "description": "DNA sequence, sid:N, or pid:N"},
                "enzymes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Enzyme names",
                },
            },
            "required": ["sequence", "enzymes"],
        }

    def format_result(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        cuts = result.get("total_cuts", 0)
        frags = result.get("fragments", [])
        return f"{cuts} cut(s), {len(frags)} fragment(s): {frags}"

    async def execute(self, params: dict[str, Any], mode: str = "direct") -> dict[str, Any]:
        inp = DigestInput(**params)
        seq = inp.sequence
        if seq.strip().lower().startswith(("sid:", "pid:")) and db.async_session_factory:
            async with db.async_session_factory() as session:
                try:
                    seq, _meta = await resolve_input(session, seq)
                except ValueError as exc:
                    return {"error": str(exc)}
        cleaned = seq.upper().replace(" ", "").replace("\n", "")

        if len(cleaned) < 1:
            return {"error": "Empty sequence"}

        from hive.cloning.enzymes import find_cut_sites, load_enzymes

        if not db.async_session_factory:
            return {"error": "Database not available"}

        async with db.async_session_factory() as session:
            enzymes = await load_enzymes(session)

        try:
            result = find_cut_sites(cleaned, inp.enzymes, enzymes, circular=inp.circular)
        except ValueError as exc:
            return {"error": str(exc)}

        fragments = result["fragments"]
        return {
            "enzymes": result["enzyme_results"],
            "fragments": fragments,
            "total_cuts": result["total_cuts"],
            "sequence_length": result["seq_len"],
            "circular": result["circular"],
            "gel_data": _compute_gel_data(fragments),
        }
