"""WatcherProcess — wraps watch_directory as a managed process."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hive.config import WatcherConfig
from hive.ps.base import Process, ProcessContext
from hive.watcher.watcher import watch_directory

if TYPE_CHECKING:
    from hive.deps import DepRegistry


class WatcherProcess(Process):
    """Long-running file watcher process."""

    name = "watcher"
    description = "File system watcher"

    def __init__(self, config: WatcherConfig, dep_registry: DepRegistry | None = None):
        self.config = config
        self.dep_registry = dep_registry

    async def run(self, ctx: ProcessContext) -> str:
        await watch_directory(
            self.config,
            stop_event=ctx.stop_event,
            dep_registry=self.dep_registry,
            ctx=ctx,
        )
        return "watcher stopped"
