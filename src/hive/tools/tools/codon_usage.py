"""Codon usage tool -- codon frequency and RSCU analysis."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from hive.molbio.codon import codon_usage, rare_codons
from hive.tools.base import Tool
from hive.tools.resolve import resolve_and_clean


class CodonUsageInput(BaseModel):
    sequence: str = Field(
        ...,
        description="Coding DNA/RNA sequence, or sid:N/pid:N",
    )
    table: int = Field(default=1, description="Codon table number (1=Standard, 11=Bacterial)")


class CodonUsageTool(Tool):
    name = "codon_usage"
    description = ("codon usage", "Analyze codon usage frequencies and RSCU for a coding DNA sequence.")
    tags = {"analysis"}
    advanced = {"table"}

    def __init__(self, **_):
        pass

    def input_schema(self) -> dict:
        schema = CodonUsageInput.model_json_schema()
        schema.pop("title", None)
        return schema

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        inp = CodonUsageInput(**params)
        result = await resolve_and_clean(inp.sequence)
        if isinstance(result, dict):
            return result
        cleaned, _meta = result

        dna = cleaned.replace("U", "T")
        if len(dna) < 3:
            return {"error": "Sequence too short (need at least 3 nucleotides)"}

        usage = codon_usage(dna, table=inp.table)
        rare = rare_codons(dna, table=inp.table)
        total = sum(e["count"] for e in usage)

        return {
            "codons": usage,
            "rare_codons": rare,
            "total_codons": total,
            "codon_table": inp.table,
        }
