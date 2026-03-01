"""Features tool — list features (parts) on a sequence."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from hive.db import session as db
from hive.db.models import Part, PartInstance, PartName
from hive.tools.base import Tool
from hive.tools.resolve import resolve_sequence


class FeaturesInput(BaseModel):
    sid: int | None = Field(default=None, description="Sequence ID (preferred)")
    sequence_name: str | None = Field(default=None, description="Sequence name (fallback)")
    type: str | None = Field(
        default=None,
        description="Filter by annotation type (e.g. CDS, promoter)",
    )


class FeaturesTool(Tool):
    name = "features"
    description = "List features (genes, promoters, etc.) on a sequence."
    widget = "text"
    tags = {"llm", "hidden", "info"}
    guidelines = "List features (genes, promoters, etc.) on a sequence."

    def __init__(self, **_):
        pass

    def input_schema(self) -> dict:
        schema = FeaturesInput.model_json_schema()
        schema.pop("title", None)
        return schema

    def llm_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "sid": {"type": "integer", "description": "Sequence ID"},
            },
            "required": ["sid"],
        }

    def format_result(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        total = result.get("total", 0)
        source = result.get("sequence_name", "")
        return f"{total} feature(s) on {source}"

    async def execute(self, params: dict[str, Any], mode: str = "direct") -> dict[str, Any]:
        inp = FeaturesInput(**params)

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

            query = (
                select(PartInstance)
                .join(Part, PartInstance.part_id == Part.id)
                .options(selectinload(PartInstance.part).selectinload(Part.names))
                .where(PartInstance.seq_id == seq_row.id)
                .where(PartInstance.annotation_type != "primer_bind")
            )
            if inp.type:
                query = query.where(PartInstance.annotation_type.ilike(inp.type))
            query = query.order_by(PartInstance.start)

            rows = (await session.execute(query)).scalars().all()

            features = [
                {
                    "pid": pi.part.id,
                    "name": pi.part.names[0].name if pi.part.names else "",
                    "type": pi.annotation_type,
                    "start": pi.start,
                    "end": pi.end,
                    "strand": pi.strand,
                }
                for pi in rows
            ]

            return {
                "features": features,
                "total": len(features),
                "sequence_name": seq_row.name,
            }
