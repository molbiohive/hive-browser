"""Translate tool — DNA/RNA to protein translation."""

from __future__ import annotations

from typing import Any

from Bio.Seq import Seq
from pydantic import BaseModel, Field

from hive.tools.base import Tool


class TranslateInput(BaseModel):
    sequence: str = Field(..., description="Nucleotide sequence (ATGC or AUGC) to translate")
    table: int = Field(default=1, description="Codon table number (1=Standard, 11=Bacterial)")


class TranslateTool(Tool):
    name = "translate"
    description = "Translate a DNA or RNA sequence to protein."
    widget = "text"
    tags = {"llm", "analysis"}
    guidelines = "Translate DNA/RNA to protein. table=1 standard, table=11 bacterial."

    def __init__(self, **_):
        pass

    def input_schema(self) -> dict:
        schema = TranslateInput.model_json_schema()
        schema.pop("title", None)
        return schema

    def format_result(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        plen = result.get("protein_length", 0)
        complete = result.get("complete", False)
        tag = " (complete ORF)" if complete else ""
        return f"Translated to {plen} amino acids{tag}"

    def summary_for_llm(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        protein = result.get("protein", "")
        plen = result.get("protein_length", 0)
        stops = result.get("stop_codons", 0)
        complete = result.get("complete", False)
        preview = protein[:50] + "..." if len(protein) > 50 else protein
        return (
            f"Protein: {plen} aa, {stops} stop codon(s), "
            f"{'complete ORF' if complete else 'partial'}. "
            f"Sequence: {preview}"
        )

    async def execute(self, params: dict[str, Any], mode: str = "direct") -> dict[str, Any]:
        inp = TranslateInput(**params)
        cleaned = inp.sequence.upper().replace(" ", "").replace("\n", "")

        # Handle RNA input
        if "U" in cleaned:
            cleaned = cleaned.replace("U", "T")

        if len(cleaned) < 3:
            return {"error": "Sequence too short to translate (need at least 3 nucleotides)"}

        try:
            protein = str(Seq(cleaned).translate(table=inp.table))
        except Exception as e:
            return {"error": f"Translation failed: {e}"}

        stops = protein.count("*")
        return {
            "protein": protein,
            "nucleotide_length": len(cleaned),
            "protein_length": len(protein),
            "stop_codons": stops,
            "complete": protein.startswith("M") and protein.endswith("*"),
            "codon_table": inp.table,
        }
