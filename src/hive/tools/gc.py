"""GC content tool -- calculate nucleotide composition."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from hive.tools.base import Tool
from hive.tools.resolve import resolve_and_clean


class GCInput(BaseModel):
    sequence: str = Field(
        ...,
        description="DNA sequence, or sid:N for Sequence ID, or pid:N for Part ID",
    )


class GCTool(Tool):
    name = "gc"
    description = ("GC content", "Calculate GC content and nucleotide composition of a DNA sequence.")
    tags = {"analysis"}

    def __init__(self, **_):
        pass

    def input_schema(self) -> dict:
        schema = GCInput.model_json_schema()
        schema.pop("title", None)
        return schema

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        inp = GCInput(**params)
        result = await resolve_and_clean(inp.sequence)
        if isinstance(result, dict):
            return result
        cleaned, _meta = result

        g = cleaned.count("G")
        c = cleaned.count("C")
        a = cleaned.count("A")
        t = cleaned.count("T")
        length = len(cleaned)

        gc_percent = (g + c) / length * 100 if length > 0 else 0

        return {
            "gc_percent": round(gc_percent, 2),
            "at_percent": round(100 - gc_percent, 2),
            "length": length,
            "g": g,
            "c": c,
            "a": a,
            "t": t,
        }
