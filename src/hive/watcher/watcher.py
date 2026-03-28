"""File system watcher -- startup scan + live monitoring."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from watchfiles import Change, awatch

from hive.config import WatcherConfig
from hive.db import session as db
from hive.watcher.ingest import ingest_file, remove_file
from hive.watcher.rules import match_file

if TYPE_CHECKING:
    from hive.deps import DepRegistry
    from hive.ps import ProcessContext

logger = logging.getLogger(__name__)


async def scan_and_ingest(
    config: WatcherConfig,
    dep_registry: DepRegistry | None = None,
    batch_size: int = 100,
    ctx: ProcessContext | None = None,
    force: bool = False,
) -> int:
    """Scan directory and ingest all parseable files. Returns count of newly indexed files."""
    root = Path(config.root).expanduser().resolve()
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

    for batch_start in range(0, total, batch_size):
        batch = files[batch_start : batch_start + batch_size]
        async with db.async_session_factory() as session:
            for path, match in batch:
                try:
                    result = await ingest_file(
                        session,
                        path,
                        match,
                        commit=False,
                        watcher_root=watcher_root,
                        force=force,
                    )
                    if result is not None:
                        indexed += 1
                except Exception as e:
                    logger.error("Failed to ingest %s: %s", path.name, e)
                    errors += 1
            await session.commit()

        done = min(batch_start + len(batch), total)
        logger.info(
            "Scan progress: %d/%d files (%d%%), %d indexed, %d errors",
            done,
            total,
            done * 100 // total,
            indexed,
            errors,
        )
        if ctx:
            await ctx.check()
        else:
            await asyncio.sleep(0)  # yield to event loop

    logger.info("Scan complete: %d indexed, %d errors out of %d files", indexed, errors, total)

    if indexed > 0 and dep_registry:
        try:
            await dep_registry.rebuild_all()
        except Exception as e:
            logger.warning("Dep rebuild failed after scan: %s", e)

    return indexed


async def watch_directory(
    config: WatcherConfig,
    stop_event: asyncio.Event | None = None,
    dep_registry: DepRegistry | None = None,
    ctx: ProcessContext | None = None,
):
    """Watch directory for changes using watchfiles (inotify/fswatch).

    Runs forever until stop_event is set or task is cancelled.
    """
    root = Path(config.root).expanduser().resolve()
    if not root.exists():
        logger.warning("Watch directory does not exist: %s", root)
        return

    watcher_root = str(root)
    logger.info("Starting file watcher on %s", root)

    async for changes in awatch(root, recursive=config.recursive, stop_event=stop_event):
        if ctx:
            await ctx.check()
        for change_type, path_str in changes:
            path = Path(path_str)

            if change_type == Change.deleted:
                async with db.async_session_factory() as session:
                    await remove_file(session, path)
                continue

            if not path.is_file():
                continue

            match = match_file(path, config.rules)

            if match.action == "parse":
                try:
                    async with db.async_session_factory() as session:
                        await ingest_file(session, path, match, watcher_root=watcher_root)
                    if dep_registry:
                        await dep_registry.rebuild_all()
                except Exception as e:
                    logger.error("Failed to ingest %s: %s", path.name, e)
            elif match.action == "log" and match.message:
                logger.debug(match.message)
