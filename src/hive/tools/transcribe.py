"""Transcribe tool — DNA to RNA transcription."""

from __future__ import annotations

from typing import Any

from Bio.Seq import Seq
from pydantic import BaseModel, Field

from hive.tools.base import Tool


class TranscribeInput(BaseModel):
    sequence: str = Field(..., description="DNA sequence (ATGC) to transcribe")


class TranscribeTool(Tool):
    name = "transcribe"
    description = "Transcribe a DNA sequence to mRNA (T→U on coding strand)."
    widget = "text"
    tags = {"llm", "analysis"}
    guidelines = "DNA to mRNA transcription (T to U)."

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

    async def execute(self, params: dict[str, Any], mode: str = "direct") -> dict[str, Any]:
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
