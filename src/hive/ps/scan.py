"""Scan processes — initial scan, rescan, and reindex."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hive.config import WatcherConfig
from hive.ps.base import Process, ProcessContext
from hive.watcher.watcher import scan_and_ingest

if TYPE_CHECKING:
    from hive.deps import DepRegistry


class ScanProcess(Process):
    """Initial directory scan on startup."""

    name = "scan"
    description = "Initial file scan"

    def __init__(self, config: WatcherConfig, dep_registry: DepRegistry | None = None):
        self.config = config
        self.dep_registry = dep_registry

    async def run(self, ctx: ProcessContext) -> str:
        count = await scan_and_ingest(self.config, dep_registry=self.dep_registry, ctx=ctx)
        return f"{count} files indexed"


class RescanProcess(Process):
    """Force full directory rescan."""

    name = "rescan"
    description = "Full directory rescan"

    def __init__(self, config: WatcherConfig, dep_registry: DepRegistry | None = None):
        self.config = config
        self.dep_registry = dep_registry

    async def run(self, ctx: ProcessContext) -> str:
        count = await scan_and_ingest(self.config, dep_registry=self.dep_registry, ctx=ctx)
        return f"{count} files indexed"


class ReindexProcess(Process):
    """Reset all file hashes and rescan (forces re-parse)."""

    name = "reindex"
    description = "Re-parse all files"

    def __init__(self, config: WatcherConfig, dep_registry: DepRegistry | None = None):
        self.config = config
        self.dep_registry = dep_registry

    async def run(self, ctx: ProcessContext) -> str:
        from sqlalchemy import update

        from hive.db.models import IndexedFile
        from hive.db.session import async_session_factory

        async with async_session_factory() as s:
            result = await s.execute(
                update(IndexedFile)
                .where(IndexedFile.status == "active")
                .values(file_hash="")
            )
            await s.commit()
            reset_count = result.rowcount

        count = await scan_and_ingest(self.config, dep_registry=self.dep_registry, ctx=ctx)
        return f"{reset_count} hashes reset, {count} files re-parsed"
