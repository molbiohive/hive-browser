"""Align tool — multiple sequence alignment using MAFFT."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from hive.db import session as db
from hive.tools.base import Tool
from hive.tools.resolve import resolve_part, resolve_sequence


class AlignInput(BaseModel):
    sids: list[int] = Field(
        default_factory=list,
        description="Sequence IDs to align",
    )
    pids: list[int] = Field(
        default_factory=list,
        description="Part IDs to include in alignment",
    )
    algorithm: str = Field(
        default="auto",
        description="MAFFT algorithm: auto, linsi, ginsi, einsi, fftns",
    )


class AlignTool(Tool):
    name = "align"
    description = "Align multiple sequences using MAFFT."
    widget = "align"
    tags = {"llm", "analysis"}
    guidelines = (
        "Multiple sequence alignment using MAFFT. Provide SIDs "
        "and/or PIDs for 2+ sequences to align."
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
                    "description": "Sequence IDs to align",
                },
                "pids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Part IDs to include in alignment",
                },
            },
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
        total = len(inp.sids) + len(inp.pids)

        if total < 2:
            return {"error": "Need at least 2 sequences (SIDs and/or PIDs) to align"}

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
            for pid in inp.pids:
                part = await resolve_part(session, pid=pid, load_names=True)
                if not part:
                    return {"error": f"Part not found for PID {pid}"}
                name = part.names[0].name if part.names else f"PID_{pid}"
                sequences.append((name, part.sequence))

        result = await self._dep.align(sequences, algorithm=inp.algorithm)
        return result
