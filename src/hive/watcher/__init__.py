"""File watcher -- monitors directories and ingests sequence files."""

from hive.watcher.watcher import scan_and_ingest, watch_directory

__all__ = ["scan_and_ingest", "watch_directory"]
