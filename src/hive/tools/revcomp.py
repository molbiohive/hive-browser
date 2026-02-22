"""Reverse complement tool — get reverse complement of a DNA sequence."""

from __future__ import annotations

from typing import Any

from Bio.Seq import Seq
from pydantic import BaseModel, Field

from hive.tools.base import Tool


class RevCompInput(BaseModel):
    sequence: str = Field(..., description="DNA sequence (ATGC)")


class RevCompTool(Tool):
    name = "revcomp"
    description = "Get the reverse complement of a DNA sequence."
    widget = "text"
    tags = {"llm", "analysis"}
    guidelines = "Reverse complement of a DNA sequence."

    def __init__(self, **_):
        pass

    def input_schema(self) -> dict:
        schema = RevCompInput.model_json_schema()
        schema.pop("title", None)
        return schema

    def format_result(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        return f"Reverse complement: {result.get('length', 0)} bp"

    def summary_for_llm(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        seq = result.get("sequence", "")
        preview = seq[:80] + "..." if len(seq) > 80 else seq
        return f"RevComp ({len(seq)} bp): {preview}"

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        inp = RevCompInput(**params)
        cleaned = inp.sequence.upper().replace(" ", "").replace("\n", "")

        if len(cleaned) < 1:
            return {"error": "Empty sequence"}

        try:
            rc = str(Seq(cleaned).reverse_complement())
        except Exception as e:
            return {"error": f"Reverse complement failed: {e}"}

        return {
            "sequence": rc,
            "length": len(rc),
        }
