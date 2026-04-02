"""Process system -- centralized registry for background tasks."""

from hive.ps.base import Process, ProcessContext, ProcessState, ProcessStoppedError
from hive.ps.dedupe import DedupeProcess
from hive.ps.match import MatchProcess
from hive.ps.prune import PruneProcess
from hive.ps.registry import ProcessRegistry
from hive.ps.scan import ReindexProcess, RescanProcess, ScanProcess
from hive.ps.watcher import WatcherProcess

__all__ = [
    "DedupeProcess",
    "MatchProcess",
    "Process",
    "ProcessContext",
    "ProcessRegistry",
    "ProcessState",
    "ProcessStoppedError",
    "PruneProcess",
    "ReindexProcess",
    "RescanProcess",
    "ScanProcess",
    "WatcherProcess",
]
