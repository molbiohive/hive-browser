"""Features tool — list features on a sequence."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from hive.db import session as db
from hive.db.models import Feature, IndexedFile, Sequence
from hive.tools.base import Tool
from hive.tools.resolve import resolve_sequence


class FeaturesInput(BaseModel):
    sid: int | None = Field(default=None, description="Sequence ID (preferred)")
    sequence_name: str | None = Field(default=None, description="Sequence name (fallback)")
    type: str | None = Field(
        default=None,
        description="Filter by feature type (e.g. CDS, promoter)",
    )


class FeaturesTool(Tool):
    name = "features"
    description = "List features (genes, promoters, etc.) on a sequence."
    widget = "text"
    tags = {"llm", "info"}
    guidelines = "List features (genes, promoters, etc.) on a sequence."

    def __init__(self, **_):
        pass

    def input_schema(self) -> dict:
        schema = FeaturesInput.model_json_schema()
        schema.pop("title", None)
        return schema

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

            query = select(Feature).where(Feature.seq_id == seq_row.id)
            if inp.type:
                query = query.where(Feature.type.ilike(inp.type))
            query = query.order_by(Feature.start)

            rows = (await session.execute(query)).scalars().all()

            features = [
                {
                    "name": f.name,
                    "type": f.type,
                    "start": f.start,
                    "end": f.end,
                    "strand": f.strand,
                }
                for f in rows
            ]

            return {
                "features": features,
                "total": len(features),
                "sequence_name": seq_row.name,
            }
