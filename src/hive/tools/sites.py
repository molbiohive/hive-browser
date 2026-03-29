"""Sites tool -- find all restriction enzymes that cut a sequence."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from hive.context import current_user_id
from hive.db import session as db
from hive.tools.base import Tool
from hive.tools.resolve import resolve_and_clean


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
    description = ("restriction sites", "Find all restriction enzymes that cut a sequence.")
    tags = {"analysis"}

    def __init__(self, **_):
        pass

    advanced = {"circular"}

    def input_schema(self) -> dict:
        schema = SitesInput.model_json_schema()
        schema.pop("title", None)
        return schema

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        inp = SitesInput(**params)
        result = await resolve_and_clean(inp.sequence)
        if isinstance(result, dict):
            return result
        cleaned, _meta = result

        if len(cleaned) < 1:
            return {"error": "Empty sequence"}

        from hive.cloning.enzymes import find_all_cutters, load_enzymes

        if not db.async_session_factory:
            return {"error": "Database not available"}

        async with db.async_session_factory() as session:
            enzymes = await load_enzymes(session)

            # Filter to user's active enzyme collection if one is selected
            from hive.cloning.collections import get_active_enzyme_names

            user_id = current_user_id.get()
            active_names = await get_active_enzyme_names(session, user_id)
            if active_names:
                active_upper = {n.upper() for n in active_names}
                enzymes = {k: v for k, v in enzymes.items() if k in active_upper}

        cutters = find_all_cutters(
            cleaned,
            enzymes,
            circular=inp.circular,
            max_cuts=inp.max_cuts,
        )

        return {
            "cutters": cutters,
            "cutters_found": len(cutters),
            "total_enzymes_scanned": len(enzymes),
        }
