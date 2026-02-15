"""Browse tool — navigate indexed project directory tree."""

from typing import Any

from pydantic import Field

from zerg.tools.base import Tool, ToolInput


class BrowseInput(ToolInput):
    path: str = Field(default="/", description="Relative path within the watched directory")


class BrowseTool(Tool):
    name = "browse"
    description = "Navigate the indexed project directory tree. Shows files with basic metadata."

    def input_schema(self) -> type[ToolInput]:
        return BrowseInput

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """List directory contents with indexed file metadata."""
        inp = BrowseInput(**params)

        # TODO: list directory, cross-reference with indexed_files table

        return {
            "path": inp.path,
            "entries": [],
        }
