"""Browse tool — navigate indexed project directory tree."""

from pathlib import Path
from typing import Any

from pydantic import Field
from sqlalchemy import select

from zerg.db import session as db
from zerg.db.models import IndexedFile
from zerg.tools.base import Tool, ToolInput


class BrowseInput(ToolInput):
    path: str = Field(default="", description="Relative path within the watched directory")


class BrowseTool(Tool):
    name = "browse"
    description = "Navigate the indexed project directory tree. Shows files with basic metadata."

    def __init__(self, watch_root: str):
        self._root = Path(watch_root).expanduser().resolve()

    def input_schema(self) -> type[ToolInput]:
        return BrowseInput

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """List directory contents with indexed file metadata."""
        inp = BrowseInput(**params)

        target = (self._root / inp.path).resolve()

        # Prevent path traversal
        if not str(target).startswith(str(self._root.resolve())):
            return {"error": "Path outside watched directory"}

        if not target.exists():
            return {"error": f"Path does not exist: {inp.path}", "entries": []}

        if not target.is_dir():
            return {"error": f"Not a directory: {inp.path}", "entries": []}

        # Collect indexed file paths for fast lookup
        indexed_paths = {}
        if db.async_session_factory:
            async with db.async_session_factory() as session:
                rows = (await session.execute(
                    select(IndexedFile.file_path, IndexedFile.format, IndexedFile.status)
                )).all()
                indexed_paths = {r.file_path: (r.format, r.status) for r in rows}

        entries = []
        for item in sorted(target.iterdir()):
            entry = {
                "name": item.name,
                "is_dir": item.is_dir(),
            }
            if item.is_file():
                entry["size"] = item.stat().st_size
                abs_path = str(item.resolve())
                if abs_path in indexed_paths:
                    fmt, status = indexed_paths[abs_path]
                    entry["indexed"] = True
                    entry["format"] = fmt
                    entry["status"] = status
                else:
                    entry["indexed"] = False
            entries.append(entry)

        rel = str(target.relative_to(self._root))
        return {
            "path": rel if rel != "." else "/",
            "entries": entries,
            "total": len(entries),
        }
