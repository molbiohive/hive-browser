"""Primers tool — list primers on a sequence."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from hive.db import session as db
from hive.db.models import IndexedFile, Primer, Sequence
from hive.tools.base import Tool


class PrimersInput(BaseModel):
    sequence_name: str = Field(..., description="Name of the sequence/plasmid")
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

    def summary_for_llm(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        primers = result.get("primers", [])
        source = result.get("sequence_name", "")
        lines = [f"Primers on {source} ({len(primers)} total):"]
        for p in primers:
            tm = f" Tm={p['tm']:.1f}" if p.get("tm") else ""
            lines.append(f"  {p['name']}: {p['sequence'][:30]}...{tm}")
        lines.append("[User sees full table — summarize, do not list.]")
        return "\n".join(lines)

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        inp = PrimersInput(**params)

        if not db.async_session_factory:
            return {"error": "Database unavailable"}

        async with db.async_session_factory() as session:
            seq_row = (await session.execute(
                select(Sequence)
                .join(IndexedFile, Sequence.file_id == IndexedFile.id)
                .where(IndexedFile.status == "active")
                .where(Sequence.name.ilike(f"%{inp.sequence_name}%"))
                .limit(1)
            )).scalar_one_or_none()

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
