"""GC content tool — calculate nucleotide composition."""

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
    description = "Calculate GC content and nucleotide composition of a DNA sequence."
    tags = {"analysis"}
    guidelines = "GC content and nucleotide composition. Accepts sequence, sid:N, or pid:N."

    def __init__(self, **_):
        pass

    def input_schema(self) -> dict:
        schema = GCInput.model_json_schema()
        schema.pop("title", None)
        return schema

    def format_result(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        gc = result.get("gc_percent", 0)
        length = result.get("length", 0)
        return f"GC content: {gc:.1f}% ({length} bp)"

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
