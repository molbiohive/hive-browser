"""Reverse complement tool -- get reverse complement of a DNA sequence."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from hive.cloning.seq import reverse_complement
from hive.tools.base import Tool
from hive.tools.resolve import resolve_and_clean


class RevCompInput(BaseModel):
    sequence: str = Field(
        ...,
        description="DNA sequence, or sid:N for Sequence ID, or pid:N for Part ID",
    )


class RevCompTool(Tool):
    name = "revcomp"
    description = ("reverse complement", "Get the reverse complement of a DNA sequence.")
    tags = {"analysis"}

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

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        inp = RevCompInput(**params)
        result = await resolve_and_clean(inp.sequence)
        if isinstance(result, dict):
            return result
        cleaned, _meta = result

        rc = reverse_complement(cleaned)

        return {
            "sequence": rc,
            "length": len(rc),
        }
