"""Profile tool — full details of a single sequence."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from zerg.db import session as db
from zerg.db.models import IndexedFile, Sequence
from zerg.tools.base import Tool, ToolInput

if TYPE_CHECKING:
    from zerg.config import Settings
    from zerg.llm.client import LLMClient


def create(config: Settings | None = None, llm_client: LLMClient | None = None) -> Tool:
    return ProfileTool()


class ProfileInput(ToolInput):
    sequence_id: int | None = Field(default=None, description="Sequence ID from database")
    name: str | None = Field(default=None, description="Sequence name to look up")


class ProfileTool(Tool):
    name = "profile"
    description = "Show full details of a specific sequence: metadata, features, primers, file info."
    widget_type = "profile"

    def format_result(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        seq = result.get("sequence")
        if not seq:
            return "Sequence not found."
        return f"{seq['name']} — {seq['size_bp']} bp, {seq['topology']}"

    def input_schema(self) -> type[ToolInput]:
        return ProfileInput

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """Fetch complete sequence profile from the database."""
        inp = ProfileInput(**params)

        if not inp.sequence_id and not inp.name:
            return {"error": "Provide either sequence_id or name"}

        if not db.async_session_factory:
            return {"error": "Database unavailable"}

        async with db.async_session_factory() as session:
            stmt = (
                select(Sequence)
                .join(IndexedFile, Sequence.file_id == IndexedFile.id)
                .options(
                    selectinload(Sequence.features),
                    selectinload(Sequence.primers),
                    selectinload(Sequence.file),
                )
                .where(IndexedFile.status == "active")
            )

            if inp.sequence_id:
                stmt = stmt.where(Sequence.id == inp.sequence_id)
            else:
                stmt = stmt.where(Sequence.name.ilike(f"%{inp.name}%"))

            seq = (await session.execute(stmt.limit(1))).scalar_one_or_none()

            if not seq:
                return {"error": f"Sequence not found: {inp.sequence_id or inp.name}"}

            return {
                "sequence": {
                    "id": seq.id,
                    "name": seq.name,
                    "size_bp": seq.size_bp,
                    "topology": seq.topology,
                    "description": seq.description,
                    "meta": seq.meta,
                },
                "features": [
                    {
                        "name": f.name,
                        "type": f.type,
                        "start": f.start,
                        "end": f.end,
                        "strand": f.strand,
                        "qualifiers": f.qualifiers,
                    }
                    for f in seq.features
                ],
                "primers": [
                    {
                        "name": p.name,
                        "sequence": p.sequence,
                        "tm": p.tm,
                        "start": p.start,
                        "end": p.end,
                        "strand": p.strand,
                    }
                    for p in seq.primers
                ],
                "file": {
                    "path": seq.file.file_path,
                    "format": seq.file.format,
                    "size": seq.file.file_size,
                    "indexed_at": seq.file.indexed_at.isoformat() if seq.file.indexed_at else None,
                },
            }
