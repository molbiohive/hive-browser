"""ORF finder tool -- 6-frame open reading frame scanner."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from hive.molbio.orf import find_orfs
from hive.tools.base import Tool
from hive.tools.resolve import resolve_and_clean


class OrfFindInput(BaseModel):
    sequence: str = Field(
        ...,
        description="DNA/RNA sequence, or sid:N/pid:N",
    )
    min_length: int = Field(default=100, description="Minimum ORF length in nucleotides")


class OrfFindTool(Tool):
    name = "orf_find"
    description = ("find ORFs", "Scan all 6 reading frames for open reading frames in a DNA sequence.")
    tags = {"analysis"}
    advanced = {"min_length"}

    def __init__(self, **_):
        pass

    def input_schema(self) -> dict:
        schema = OrfFindInput.model_json_schema()
        schema.pop("title", None)
        return schema

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        inp = OrfFindInput(**params)
        result = await resolve_and_clean(inp.sequence)
        if isinstance(result, dict):
            return result
        cleaned, _meta = result

        dna = cleaned.replace("U", "T")
        if len(dna) < inp.min_length:
            return {"error": f"Sequence too short ({len(dna)} nt, minimum {inp.min_length})"}

        orfs = find_orfs(dna, min_length=inp.min_length)

        return {
            "orfs": [
                {
                    "frame": o["frame"],
                    "start": o["start"],
                    "end": o["end"],
                    "length_nt": o["length_nt"],
                    "length_aa": o["length_aa"],
                    "status": o["status"],
                    "protein": o["protein"],
                }
                for o in orfs
            ],
            "total_orfs": len(orfs),
            "sequence_length": len(dna),
        }
