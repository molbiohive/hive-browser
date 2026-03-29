"""Translate tool -- DNA/RNA to protein translation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from hive.cloning.seq import translate as seq_translate
from hive.tools.base import Tool
from hive.tools.resolve import resolve_and_clean


class TranslateInput(BaseModel):
    sequence: str = Field(
        ...,
        description="DNA/RNA sequence, or sid:N for Sequence ID, or pid:N for Part ID",
    )
    table: int = Field(default=1, description="Codon table number (1=Standard, 11=Bacterial)")


class TranslateTool(Tool):
    name = "translate"
    description = ("DNA to protein", "Translate a DNA or RNA sequence to protein.")
    tags = {"analysis"}
    advanced = {"table"}

    def __init__(self, **_):
        pass

    def input_schema(self) -> dict:
        schema = TranslateInput.model_json_schema()
        schema.pop("title", None)
        return schema

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        inp = TranslateInput(**params)
        result = await resolve_and_clean(inp.sequence)
        if isinstance(result, dict):
            return result
        cleaned, _meta = result

        # Handle RNA input
        if "U" in cleaned:
            cleaned = cleaned.replace("U", "T")

        if len(cleaned) < 3:
            return {"error": "Sequence too short to translate (need at least 3 nucleotides)"}

        protein = seq_translate(cleaned, table=inp.table)

        stops = protein.count("*")
        return {
            "protein": protein,
            "nucleotide_length": len(cleaned),
            "protein_length": len(protein),
            "stop_codons": stops,
            "complete": protein.startswith("M") and protein.endswith("*"),
            "codon_table": inp.table,
        }
