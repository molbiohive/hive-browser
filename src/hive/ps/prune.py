"""Prune process -- remove records for missing files in background."""

from __future__ import annotations

import logging
from pathlib import Path

from hive.admin.db import prune
from hive.config import Settings
from hive.db import session as db
from hive.ps.base import Process, ProcessContext
from hive.utils import timed

logger = logging.getLogger(__name__)


class PruneProcess(Process):
    """Remove records for files that no longer exist on disk."""

    name = "prune"
    description = "Remove orphan file records"

    def __init__(self, config: Settings):
        self._watcher_root = config.watcher.root
        self._archive_dir = str(Path(config.data_root).expanduser() / "archive")

    async def run(self, ctx: ProcessContext) -> str:
        if not db.async_session_factory:
            return "Database unavailable"
        with timed() as t:
            async with db.async_session_factory() as session:
                result = await prune(
                    session,
                    self._watcher_root,
                    archive_dir=self._archive_dir,
                    dry_run=False,
                )
        return f"{result['pruned']} orphans removed in {t}"
