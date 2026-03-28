"""Process system — centralized registry for background tasks."""

from hive.ps.base import Process, ProcessContext, ProcessState, ProcessStoppedError
from hive.ps.match import MatchProcess
from hive.ps.registry import ProcessRegistry
from hive.ps.scan import ReindexProcess, RescanProcess, ScanProcess
from hive.ps.watcher import WatcherProcess

__all__ = [
    "MatchProcess",
    "Process",
    "ProcessContext",
    "ProcessRegistry",
    "ProcessState",
    "ProcessStoppedError",
    "ReindexProcess",
    "RescanProcess",
    "ScanProcess",
    "WatcherProcess",
]
