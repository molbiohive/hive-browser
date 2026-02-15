"""Profile tool — full details of a single sequence."""

from typing import Any

from pydantic import Field

from zerg.tools.base import Tool, ToolInput


class ProfileInput(ToolInput):
    sequence_id: int | None = Field(default=None, description="Sequence ID from database")
    name: str | None = Field(default=None, description="Sequence name to look up")


class ProfileTool(Tool):
    name = "profile"
    description = "Show full details of a specific sequence: metadata, features, primers, file info."

    def input_schema(self) -> type[ToolInput]:
        return ProfileInput

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """Fetch complete sequence profile from the database."""
        inp = ProfileInput(**params)

        # TODO: query sequences + features + primers by id or name

        return {
            "sequence": None,
            "features": [],
            "primers": [],
            "file_info": None,
        }
