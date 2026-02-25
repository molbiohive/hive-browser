"""Profile tool — full details of a single sequence."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from hive.config import display_file_path
from hive.db import session as db
from hive.tools.base import Tool
from hive.tools.resolve import resolve_sequence


class ProfileInput(BaseModel):
    sid: int | None = Field(default=None, description="Sequence ID (preferred)")
    name: str | None = Field(default=None, description="Sequence name (fallback)")


class ProfileTool(Tool):
    name = "profile"
    description = (
        "Show full details of a specific sequence: "
        "metadata, features, primers, file info."
    )
    widget = "profile"
    tags = {"llm", "info"}
    guidelines = "Full sequence details. Use sid (from search results) or name."

    def __init__(self, **_):
        pass

    def input_schema(self) -> dict:
        schema = ProfileInput.model_json_schema()
        schema.pop("title", None)
        return schema

    def format_result(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        seq = result.get("sequence")
        if not seq:
            return "Sequence not found."
        return f"{seq['name']} — {seq['size_bp']} bp, {seq['topology']}"

    async def execute(self, params: dict[str, Any], mode: str = "direct") -> dict[str, Any]:
        """Fetch complete sequence profile from the database."""
        inp = ProfileInput(**params)

        if inp.sid is None and not inp.name:
            return {"error": "Provide either sid or name"}

        if not db.async_session_factory:
            return {"error": "Database unavailable"}

        async with db.async_session_factory() as session:
            seq = await resolve_sequence(
                session,
                sid=inp.sid,
                name=inp.name,
                load_features=True,
                load_primers=True,
                load_file=True,
            )

            if not seq:
                return {"error": f"Sequence not found: {inp.sid or inp.name}"}

            return {
                "sequence": {
                    "sid": seq.id,
                    "name": seq.name,
                    "size_bp": seq.size_bp,
                    "topology": seq.topology,
                    "description": seq.description,
                    "meta": seq.meta,
                    "sequence_data": seq.sequence,
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
                    "path": display_file_path(seq.file.file_path),
                    "format": seq.file.format,
                    "size": seq.file.file_size,
                    "indexed_at": seq.file.indexed_at.isoformat() if seq.file.indexed_at else None,
                },
            }
