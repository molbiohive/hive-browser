"""File system watcher — startup scan + live monitoring."""

import asyncio
import logging
from pathlib import Path

from watchfiles import Change, awatch

from hive.config import WatcherConfig
from hive.db.session import async_session_factory
from hive.watcher.ingest import ingest_file, remove_file
from hive.watcher.rules import match_file

logger = logging.getLogger(__name__)


async def scan_and_ingest(
    config: WatcherConfig,
    blast_db_path: str | None = None,
    batch_size: int = 100,
) -> int:
    """Scan directory and ingest all parseable files. Returns count of newly indexed files."""
    root = Path(config.root)
    if not root.exists():
        logger.warning("Watch directory does not exist: %s", root)
        return 0

    pattern = "**/*" if config.recursive else "*"

    # Collect parseable files first
    files = []
    for path in root.glob(pattern):
        if not path.is_file():
            continue
        match = match_file(path, config.rules)
        if match.action == "parse":
            files.append((path, match))
        elif match.action == "log" and match.message:
            logger.debug(match.message)

    total = len(files)
    if total == 0:
        logger.info("Scan complete: no parseable files in %s", root)
        return 0

    watcher_root = str(root)
    logger.info("Scan started: %d parseable files in %s", total, root)

    indexed = 0
    errors = 0
    batch_count = 0
    session = None

    try:
        for i, (path, match) in enumerate(files, 1):
            if session is None:
                session = async_session_factory()
                session = await session.__aenter__()

            try:
                result = await ingest_file(session, path, match, commit=False, watcher_root=watcher_root)
                if result is not None:
                    indexed += 1
            except Exception as e:
                logger.error("Failed to ingest %s: %s", path.name, e)
                errors += 1

            batch_count += 1

            if batch_count >= batch_size or i == total:
                await session.commit()
                await session.__aexit__(None, None, None)
                session = None
                batch_count = 0
                logger.info(
                    "Scan progress: %d/%d files (%d%%), %d indexed, %d errors",
                    i, total, i * 100 // total, indexed, errors,
                )
                await asyncio.sleep(0)  # yield to event loop
    finally:
        if session is not None:
            await session.__aexit__(None, None, None)

    logger.info("Scan complete: %d indexed, %d errors out of %d files", indexed, errors, total)

    if indexed > 0 and blast_db_path:
        try:
            from hive.tools.blast import build_blast_index
            await build_blast_index(blast_db_path)
        except Exception as e:
            logger.warning("BLAST index rebuild failed after scan: %s", e)

    return indexed


async def watch_directory(
    config: WatcherConfig,
    stop_event: asyncio.Event | None = None,
    blast_db_path: str | None = None,
):
    """Watch directory for changes using watchfiles (inotify/fswatch).

    Runs forever until stop_event is set or task is cancelled.
    """
    root = Path(config.root)
    if not root.exists():
        logger.warning("Watch directory does not exist: %s", root)
        return

    watcher_root = str(root)
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
                        await ingest_file(session, path, match, watcher_root=watcher_root)
                    if blast_db_path:
                        from hive.tools.blast import build_blast_index
                        await build_blast_index(blast_db_path)
                except Exception as e:
                    logger.error("Failed to ingest %s: %s", path.name, e)
            elif match.action == "log" and match.message:
                logger.debug(match.message)
