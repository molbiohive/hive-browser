"""Align tool — multiple sequence alignment using MAFFT."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from hive.db import session as db
from hive.tools.base import Tool
from hive.tools.resolve import resolve_sequence


class AlignInput(BaseModel):
    sids: list[int] = Field(
        default_factory=list,
        description="Sequence IDs to align",
    )
    algorithm: str = Field(
        default="auto",
        description="MAFFT algorithm: auto, linsi, ginsi, einsi, fftns",
    )


class AlignTool(Tool):
    name = "align"
    description = "Align multiple sequences using MAFFT."
    widget = "text"
    tags = {"llm", "hidden", "analysis"}
    guidelines = (
        "Multiple sequence alignment using MAFFT. Provide SIDs "
        "(integers from search results) for 2+ sequences to align."
    )

    def __init__(self, config=None, **_):
        self._dep = None
        if config:
            from hive.deps.mafft import MafftDep
            self._dep = MafftDep(config.deps.mafft.bin_dir)

    def input_schema(self) -> dict:
        schema = AlignInput.model_json_schema()
        schema.pop("title", None)
        return schema

    def llm_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "sids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Sequence IDs to align (at least 2)",
                },
            },
            "required": ["sids"],
        }

    def format_result(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        count = result.get("count", 0)
        return f"Aligned {count} sequences."

    async def execute(self, params: dict[str, Any], mode: str = "direct") -> dict[str, Any]:
        if not self._dep:
            return {"error": "MAFFT not configured"}

        inp = AlignInput(**params)

        if len(inp.sids) < 2:
            return {"error": "Need at least 2 SIDs to align"}

        if not db.async_session_factory:
            return {"error": "Database unavailable"}

        # Resolve sequences from DB
        sequences: list[tuple[str, str]] = []
        async with db.async_session_factory() as session:
            for sid in inp.sids:
                seq = await resolve_sequence(session, sid=sid)
                if not seq:
                    return {"error": f"Sequence not found for SID {sid}"}
                sequences.append((seq.name, seq.sequence))

        result = await self._dep.align(sequences, algorithm=inp.algorithm)
        return result
