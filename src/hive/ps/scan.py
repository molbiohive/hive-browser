"""Scan processes — initial scan, rescan, and reindex."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

from hive.config import WatcherConfig
from hive.ps.base import Process, ProcessContext
from hive.watcher.watcher import scan_and_ingest

if TYPE_CHECKING:
    from hive.deps import DepRegistry

logger = logging.getLogger(__name__)

# Minimum seconds between startup scans (20 minutes)
SCAN_COOLDOWN = 1200


def _token_path(config: WatcherConfig) -> Path:
    """Return path for the .last_scan timestamp file next to the watch root."""
    root = Path(config.root).expanduser().resolve()
    return root / ".last_scan"


def _read_last_scan(config: WatcherConfig) -> float:
    """Read last scan timestamp, or 0 if missing."""
    path = _token_path(config)
    try:
        return float(path.read_text().strip())
    except (FileNotFoundError, ValueError):
        return 0.0


def _write_last_scan(config: WatcherConfig) -> None:
    """Write current time as last scan timestamp."""
    path = _token_path(config)
    try:
        path.write_text(str(time.time()))
    except OSError as e:
        logger.warning("Could not write scan token: %s", e)


class ScanProcess(Process):
    """Initial directory scan on startup."""

    name = "scan"
    description = "Initial file scan"

    def __init__(self, config: WatcherConfig, dep_registry: DepRegistry | None = None):
        self.config = config
        self.dep_registry = dep_registry

    async def run(self, ctx: ProcessContext) -> str:
        last = _read_last_scan(self.config)
        elapsed = time.time() - last
        if elapsed < SCAN_COOLDOWN:
            remaining = int(SCAN_COOLDOWN - elapsed)
            logger.info("Scan skipped: last scan %ds ago (cooldown %ds)", int(elapsed), SCAN_COOLDOWN)
            return f"Skipped, last scan {int(elapsed)}s ago ({remaining}s remaining)"

        count = await scan_and_ingest(self.config, dep_registry=self.dep_registry, ctx=ctx)
        _write_last_scan(self.config)
        return f"{count} files indexed"


class RescanProcess(Process):
    """Force full directory rescan (ignores cooldown)."""

    name = "rescan"
    description = "Full directory rescan"

    def __init__(self, config: WatcherConfig, dep_registry: DepRegistry | None = None):
        self.config = config
        self.dep_registry = dep_registry

    async def run(self, ctx: ProcessContext) -> str:
        count = await scan_and_ingest(self.config, dep_registry=self.dep_registry, ctx=ctx)
        _write_last_scan(self.config)
        return f"{count} files indexed"


class ReindexProcess(Process):
    """Reset all file hashes and rescan (forces re-parse, ignores cooldown)."""

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
        _write_last_scan(self.config)
        return f"{reset_count} hashes reset, {count} files re-parsed"
