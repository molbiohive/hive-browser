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
    tags = {"llm", "hidden", "analysis"}
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

    async def execute(self, params: dict[str, Any], mode: str = "direct") -> dict[str, Any]:
        inp = RevCompInput(**params)
        cleaned = inp.sequence.upper().replace(" ", "").replace("\n", "")

        if len(cleaned) < 1:
            return {"error": "Empty sequence"}

        rc = str(Seq(cleaned).reverse_complement())

        return {
            "sequence": rc,
            "length": len(rc),
        }
