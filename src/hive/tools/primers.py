"""Primers tool — list primers on a sequence."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from hive.db import session as db
from hive.db.models import IndexedFile, Primer, Sequence
from hive.tools.base import Tool
from hive.tools.resolve import resolve_sequence


class PrimersInput(BaseModel):
    sid: int | None = Field(default=None, description="Sequence ID (preferred)")
    sequence_name: str | None = Field(default=None, description="Sequence name (fallback)")
    name: str | None = Field(default=None, description="Filter by primer name")


class PrimersTool(Tool):
    name = "primers"
    description = "List primers on a sequence."
    widget = "text"
    tags = {"llm", "info"}
    guidelines = "List primers on a sequence."

    def __init__(self, **_):
        pass

    def input_schema(self) -> dict:
        schema = PrimersInput.model_json_schema()
        schema.pop("title", None)
        return schema

    def format_result(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        total = result.get("total", 0)
        source = result.get("sequence_name", "")
        return f"{total} primer(s) on {source}"

    async def execute(self, params: dict[str, Any], mode: str = "direct") -> dict[str, Any]:
        inp = PrimersInput(**params)

        if inp.sid is None and not inp.sequence_name:
            return {"error": "Provide either sid or sequence_name"}

        if not db.async_session_factory:
            return {"error": "Database unavailable"}

        async with db.async_session_factory() as session:
            seq_row = await resolve_sequence(
                session, sid=inp.sid, name=inp.sequence_name,
            )

            if not seq_row:
                return {"error": f"Sequence not found: {inp.sequence_name}"}

            query = select(Primer).where(Primer.seq_id == seq_row.id)
            if inp.name:
                query = query.where(Primer.name.ilike(f"%{inp.name}%"))
            query = query.order_by(Primer.start)

            rows = (await session.execute(query)).scalars().all()

            primers = [
                {
                    "name": p.name,
                    "sequence": p.sequence,
                    "tm": p.tm,
                    "start": p.start,
                    "end": p.end,
                    "strand": p.strand,
                }
                for p in rows
            ]

            return {
                "primers": primers,
                "total": len(primers),
                "sequence_name": seq_row.name,
            }
