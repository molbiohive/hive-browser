"""Status tool — system health, indexed file counts, service availability."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from zerg.db import session as db
from zerg.db.models import Feature, IndexedFile, Primer, Sequence
from zerg.tools.base import Tool


class StatusTool(Tool):
    name = "status"
    description = "Show system status: indexed files count, database health, LLM availability."
    widget = "status"
    tags = {"info"}

    def __init__(self, llm_client=None, **_):
        self._llm = llm_client

    def input_schema(self) -> dict:
        return {"type": "object", "properties": {}}

    def format_result(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        return f"{result.get('sequences', 0)} sequences indexed"

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """Gather system status information."""
        db_connected = False
        counts = {"indexed_files": 0, "sequences": 0, "features": 0, "primers": 0}

        if db.async_session_factory:
            try:
                async with db.async_session_factory() as s:
                    counts["indexed_files"] = (await s.execute(
                        select(func.count()).select_from(IndexedFile)
                        .where(IndexedFile.status == "active")
                    )).scalar()
                    counts["sequences"] = (await s.execute(
                        select(func.count()).select_from(Sequence)
                    )).scalar()
                    counts["features"] = (await s.execute(
                        select(func.count()).select_from(Feature)
                    )).scalar()
                    counts["primers"] = (await s.execute(
                        select(func.count()).select_from(Primer)
                    )).scalar()
                db_connected = True
            except Exception:
                pass

        llm_available = False
        if self._llm:
            try:
                llm_available = await self._llm.health()
            except Exception:
                pass

        return {
            **counts,
            "database_connected": db_connected,
            "llm_available": llm_available,
        }
