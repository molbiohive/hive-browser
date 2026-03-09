"""Reverse complement tool — get reverse complement of a DNA sequence."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from hive.cloning.seq import reverse_complement

from hive.db import session as db
from hive.tools.base import Tool
from hive.tools.resolve import resolve_input


class RevCompInput(BaseModel):
    sequence: str = Field(
        ...,
        description="DNA sequence, or sid:N for Sequence ID, or pid:N for Part ID",
    )


class RevCompTool(Tool):
    name = "revcomp"
    description = "Get the reverse complement of a DNA sequence."
    widget = "text"
    tags = {"llm", "hidden", "analysis"}
    guidelines = "Reverse complement. Accepts sequence, sid:N, or pid:N."

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
        seq = inp.sequence
        if seq.strip().lower().startswith(("sid:", "pid:")) and db.async_session_factory:
            async with db.async_session_factory() as session:
                try:
                    seq, _meta = await resolve_input(session, seq)
                except ValueError as exc:
                    return {"error": str(exc)}
        cleaned = seq.upper().replace(" ", "").replace("\n", "")

        if len(cleaned) < 1:
            return {"error": "Empty sequence"}

        rc = reverse_complement(cleaned)

        return {
            "sequence": rc,
            "length": len(rc),
        }
