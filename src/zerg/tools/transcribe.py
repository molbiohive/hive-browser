"""Transcribe tool — DNA to RNA transcription."""

from __future__ import annotations

from typing import Any

from Bio.Seq import Seq
from pydantic import BaseModel, Field

from zerg.tools.base import Tool


class TranscribeInput(BaseModel):
    sequence: str = Field(..., description="DNA sequence (ATGC) to transcribe")


class TranscribeTool(Tool):
    name = "transcribe"
    description = "Transcribe a DNA sequence to mRNA (T→U on coding strand)."
    widget = "text"
    tags = {"llm", "analysis"}
    guidelines = (
        "Put raw DNA sequence (ATGC) in `sequence`. "
        "Input should be the coding (sense) strand. "
        "Use extract first to get feature sequences from a plasmid."
    )

    def __init__(self, **_):
        pass

    def input_schema(self) -> dict:
        schema = TranscribeInput.model_json_schema()
        schema.pop("title", None)
        return schema

    def format_result(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        return f"Transcribed to {result.get('length', 0)} nt mRNA"

    def summary_for_llm(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        rna = result.get("rna", "")
        preview = rna[:80] + "..." if len(rna) > 80 else rna
        return f"mRNA ({len(rna)} nt): {preview}"

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        inp = TranscribeInput(**params)
        cleaned = inp.sequence.upper().replace(" ", "").replace("\n", "")

        if len(cleaned) < 1:
            return {"error": "Empty sequence"}

        try:
            rna = str(Seq(cleaned).transcribe())
        except Exception as e:
            return {"error": f"Transcription failed: {e}"}

        return {
            "rna": rna,
            "length": len(rna),
        }
