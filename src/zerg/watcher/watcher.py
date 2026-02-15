"""File system watcher — startup scan + live monitoring."""

import asyncio
import logging
from pathlib import Path

from watchfiles import Change, awatch

from zerg.config import WatcherConfig
from zerg.db.session import async_session_factory
from zerg.watcher.ingest import ingest_file, remove_file
from zerg.watcher.rules import match_file

logger = logging.getLogger(__name__)


async def scan_and_ingest(config: WatcherConfig) -> int:
    """Scan directory and ingest all parseable files. Returns count of newly indexed files."""
    root = Path(config.root)
    if not root.exists():
        logger.warning("Watch directory does not exist: %s", root)
        return 0

    pattern = "**/*" if config.recursive else "*"
    indexed = 0

    for path in root.glob(pattern):
        if not path.is_file():
            continue

        match = match_file(path, config.rules)

        if match.action == "parse":
            try:
                async with async_session_factory() as session:
                    result = await ingest_file(session, path, match)
                    if result is not None:
                        indexed += 1
            except Exception as e:
                logger.error("Failed to ingest %s: %s", path.name, e)
        elif match.action == "log" and match.message:
            logger.debug(match.message)

    logger.info("Scan complete: %d files indexed in %s", indexed, root)
    return indexed


async def watch_directory(config: WatcherConfig, stop_event: asyncio.Event | None = None):
    """Watch directory for changes using watchfiles (inotify/fswatch).

    Runs forever until stop_event is set or task is cancelled.
    """
    root = Path(config.root)
    if not root.exists():
        logger.warning("Watch directory does not exist: %s", root)
        return

    logger.info("Starting file watcher on %s", root)

    async for changes in awatch(root, recursive=config.recursive, stop_event=stop_event):
        for change_type, path_str in changes:
            path = Path(path_str)

            if change_type == Change.deleted:
                async with async_session_factory() as session:
                    await remove_file(session, path)
                continue

            if not path.is_file():
                continue

            match = match_file(path, config.rules)

            if match.action == "parse":
                try:
                    async with async_session_factory() as session:
                        await ingest_file(session, path, match)
                except Exception as e:
                    logger.error("Failed to ingest %s: %s", path.name, e)
            elif match.action == "log" and match.message:
                logger.debug(match.message)
