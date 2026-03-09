"""Sites tool -- find all restriction enzymes that cut a sequence."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from hive.db import session as db
from hive.tools.base import Tool
from hive.tools.resolve import resolve_input


class SitesInput(BaseModel):
    sequence: str = Field(
        ...,
        description="DNA sequence, or sid:N for Sequence ID, or pid:N for Part ID",
    )
    circular: bool = Field(
        default=True,
        description="True for circular (plasmid), False for linear",
    )
    max_cuts: int | None = Field(
        default=None,
        description="Only return enzymes with at most this many cuts (1 = unique cutters)",
    )


class SitesTool(Tool):
    name = "sites"
    description = "Find all restriction enzymes that cut a sequence."
    widget = "text"
    tags = {"llm", "analysis"}
    guidelines = "Find all restriction enzymes that cut a sequence. Use max_cuts=1 for unique cutters."

    def __init__(self, **_):
        pass

    def input_schema(self) -> dict:
        schema = SitesInput.model_json_schema()
        schema.pop("title", None)
        return schema

    def llm_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "sequence": {"type": "string", "description": "DNA sequence, sid:N, or pid:N"},
                "max_cuts": {"type": "integer", "description": "Max cuts filter (1 = unique cutters)"},
            },
            "required": ["sequence"],
        }

    def format_result(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        found = result.get("cutters_found", 0)
        total = result.get("total_enzymes_scanned", 0)
        unique = sum(1 for c in result.get("cutters", []) if c["num_cuts"] == 1)
        return f"Found {found} enzymes that cut ({unique} unique cutters) out of {total} scanned"

    async def execute(self, params: dict[str, Any], mode: str = "direct") -> dict[str, Any]:
        inp = SitesInput(**params)
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

        from hive.cloning.enzymes import find_all_cutters, load_enzymes

        if not db.async_session_factory:
            return {"error": "Database not available"}

        async with db.async_session_factory() as session:
            enzymes = await load_enzymes(session)

        cutters = find_all_cutters(
            cleaned, enzymes, circular=inp.circular, max_cuts=inp.max_cuts,
        )

        return {
            "cutters": cutters,
            "cutters_found": len(cutters),
            "total_enzymes_scanned": len(enzymes),
        }
