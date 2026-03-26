"""Transcribe tool — DNA to RNA transcription."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from hive.cloning.seq import transcribe as seq_transcribe

from hive.tools.base import Tool
from hive.tools.resolve import resolve_and_clean


class TranscribeInput(BaseModel):
    sequence: str = Field(
        ...,
        description="DNA sequence, or sid:N for Sequence ID, or pid:N for Part ID",
    )


class TranscribeTool(Tool):
    name = "transcribe"
    description = "Transcribe a DNA sequence to mRNA (T→U on coding strand)."
    tags = {"analysis"}
    guidelines = "DNA to mRNA transcription (T to U). Accepts sequence, sid:N, or pid:N."

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

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        inp = TranscribeInput(**params)
        result = await resolve_and_clean(inp.sequence)
        if isinstance(result, dict):
            return result
        cleaned, _meta = result

        rna = seq_transcribe(cleaned)

        return {
            "rna": rna,
            "length": len(rna),
        }
