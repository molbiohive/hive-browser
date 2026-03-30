"""Digest tool -- restriction enzyme digestion analysis."""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, Field

from hive.db import session as db
from hive.tools.base import Tool
from hive.tools.resolve import resolve_and_clean

# NEB 1kb+ DNA Ladder -- (size_bp, relative_intensity)
_1KB_PLUS_LADDER = [
    (10000, 0.4),
    (8000, 0.3),
    (6000, 0.3),
    (5000, 0.35),
    (4000, 0.35),
    (3000, 1.0),
    (2000, 0.4),
    (1500, 0.4),
    (1000, 1.0),
    (500, 0.5),
    (250, 0.3),
]


def _band_position(size: int, log_max: float, log_min: float) -> float:
    """Log-linear migration position, clamped to [0.05, 0.95]."""
    if size <= 0:
        return 0.95
    pos = (log_max - math.log10(size)) / (log_max - log_min)
    return max(0.05, min(0.95, pos))


def _make_bands(fragments: list[int], log_max: float, log_min: float) -> list[dict]:
    """Build band dicts for a set of fragments."""
    max_frag = max(fragments) if fragments else 1
    return [
        {
            "position": _band_position(size, log_max, log_min),
            "intensity": max(0.3, min(1.0, size / max_frag)),
            "size": size,
            "name": f"{size} bp",
        }
        for size in sorted(fragments, reverse=True)
    ]


def _compute_gel_data(reactions: list[dict]) -> dict:
    """Build GelData for Hatchlings GelViewer with one lane per reaction."""
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

    lanes = [{"label": "1kb+ Ladder", "bands": ladder_bands, "isLadder": True}]
    for rxn in reactions:
        lanes.append(
            {
                "label": rxn["name"],
                "bands": _make_bands(rxn["fragments"], log_max, log_min),
            }
        )

    return {
        "lanes": lanes,
        "gelType": "agarose",
        "stain": "ethidium",
    }


class DigestInput(BaseModel):
    sequence: str = Field(
        ...,
        description="DNA sequence, or sid:N for Sequence ID, or pid:N for Part ID",
    )
    reactions: list[str] = Field(
        ...,
        description='Reactions, e.g. ["EcoRI", "BsaI", "EcoRI+BsaI"]. Use + for co-digestion.',
    )
    circular: bool = Field(
        default=True,
        description="True for circular (plasmid), False for linear",
    )


class DigestTool(Tool):
    name = "digest"
    description = ("restriction digest", "Find restriction enzyme cut sites and calculate fragment sizes.")
    tags = {"analysis"}
    advanced = {"circular"}

    def __init__(self, **_):
        pass

    def input_schema(self) -> dict:
        schema = DigestInput.model_json_schema()
        schema.pop("title", None)
        return schema

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        inp = DigestInput(**params)
        result = await resolve_and_clean(inp.sequence)
        if isinstance(result, dict):
            return result
        cleaned, _meta = result

        if len(cleaned) < 1:
            return {"error": "Empty sequence"}

        from hive.libs.enzymes import load_enzymes
        from hive.molbio.enzymes import find_cut_sites

        if not db.async_session_factory:
            return {"error": "Database not available"}

        async with db.async_session_factory() as session:
            enzymes = await load_enzymes(session)

        reaction_results = []
        for rxn_str in inp.reactions:
            enzyme_names = [e.strip() for e in rxn_str.split("+") if e.strip()]
            try:
                result = find_cut_sites(cleaned, enzyme_names, enzymes, circular=inp.circular)
            except ValueError as exc:
                return {"error": str(exc)}

            reaction_results.append(
                {
                    "name": rxn_str,
                    "enzymes": result["enzyme_results"],
                    "fragments": result["fragments"],
                    "total_cuts": result["total_cuts"],
                }
            )

        return {
            "reactions": reaction_results,
            "sequence_length": len(cleaned),
            "circular": inp.circular,
            "gel_data": _compute_gel_data(reaction_results),
        }
