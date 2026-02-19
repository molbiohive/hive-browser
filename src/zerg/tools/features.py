"""Features tool — list features on a sequence."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from zerg.db import session as db
from zerg.db.models import Feature, IndexedFile, Sequence
from zerg.tools.base import Tool


class FeaturesInput(BaseModel):
    sequence_name: str = Field(..., description="Name of the sequence/plasmid")
    type: str | None = Field(
        default=None,
        description="Filter by feature type (e.g. CDS, promoter)",
    )


class FeaturesTool(Tool):
    name = "features"
    description = "List features (genes, promoters, etc.) on a sequence."
    widget = "text"
    tags = {"llm", "info"}
    guidelines = (
        "Use to list all features on a sequence before extracting one. "
        "Put the plasmid/sequence name in `sequence_name`. "
        "Optionally filter by type (CDS, promoter, terminator, etc.)."
    )

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

    def summary_for_llm(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        features = result.get("features", [])
        source = result.get("sequence_name", "")
        lines = [f"Features on {source} ({len(features)} total):"]
        for f in features:
            strand = "+" if f["strand"] == 1 else "-" if f["strand"] == -1 else "."
            lines.append(f"  {f['name']} ({f['type']}) {f['start']}..{f['end']} [{strand}]")
        return "\n".join(lines)

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        inp = FeaturesInput(**params)

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
