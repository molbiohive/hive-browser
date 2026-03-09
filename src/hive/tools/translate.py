"""Translate tool — DNA/RNA to protein translation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from hive.cloning.seq import translate as seq_translate

from hive.db import session as db
from hive.tools.base import Tool
from hive.tools.resolve import resolve_input


class TranslateInput(BaseModel):
    sequence: str = Field(
        ...,
        description="DNA/RNA sequence, or sid:N for Sequence ID, or pid:N for Part ID",
    )
    table: int = Field(default=1, description="Codon table number (1=Standard, 11=Bacterial)")


class TranslateTool(Tool):
    name = "translate"
    description = "Translate a DNA or RNA sequence to protein."
    widget = "text"
    tags = {"llm", "hidden", "analysis"}
    guidelines = (
        "Translate DNA/RNA to protein. Accepts sequence, sid:N, or pid:N."
        " table=1 standard, table=11 bacterial."
    )

    def __init__(self, **_):
        pass

    def input_schema(self) -> dict:
        schema = TranslateInput.model_json_schema()
        schema.pop("title", None)
        return schema

    def llm_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "sequence": {"type": "string", "description": "DNA/RNA sequence, sid:N, or pid:N"},
            },
            "required": ["sequence"],
        }

    def format_result(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        plen = result.get("protein_length", 0)
        complete = result.get("complete", False)
        tag = " (complete ORF)" if complete else ""
        return f"Translated to {plen} amino acids{tag}"

    async def execute(self, params: dict[str, Any], mode: str = "direct") -> dict[str, Any]:
        inp = TranslateInput(**params)
        seq = inp.sequence
        if seq.strip().lower().startswith(("sid:", "pid:")) and db.async_session_factory:
            async with db.async_session_factory() as session:
                try:
                    seq, _meta = await resolve_input(session, seq)
                except ValueError as exc:
                    return {"error": str(exc)}
        cleaned = seq.upper().replace(" ", "").replace("\n", "")

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
