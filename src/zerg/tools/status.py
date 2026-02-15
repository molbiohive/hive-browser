"""Status tool — system health, indexed file counts, LLM status."""

from typing import Any

from zerg.tools.base import Tool, ToolInput


class StatusInput(ToolInput):
    pass


class StatusTool(Tool):
    name = "status"
    description = "Show system status: indexed files count, database health, LLM availability."

    def input_schema(self) -> type[ToolInput]:
        return StatusInput

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """Gather system status information."""
        # TODO: query actual counts and health checks

        return {
            "indexed_files": 0,
            "sequences": 0,
            "features": 0,
            "blast_index_ready": False,
            "llm_available": False,
            "database_connected": False,
        }
