"""GC content tool — calculate nucleotide composition."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from hive.tools.base import Tool


class GCInput(BaseModel):
    sequence: str = Field(..., description="Nucleotide sequence (ATGC)")


class GCTool(Tool):
    name = "gc"
    description = "Calculate GC content and nucleotide composition of a DNA sequence."
    widget = "text"
    tags = {"llm", "analysis"}
    guidelines = "GC content and nucleotide composition."

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

    async def execute(self, params: dict[str, Any], mode: str = "direct") -> dict[str, Any]:
        inp = GCInput(**params)
        cleaned = inp.sequence.upper().replace(" ", "").replace("\n", "")

        if len(cleaned) < 1:
            return {"error": "Empty sequence"}

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
