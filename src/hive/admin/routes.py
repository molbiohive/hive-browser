"""Admin API endpoints — protected by bearer token."""

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select, text

from hive.db import session as db
from hive.db.models import Feature, IndexedFile, Primer, Sequence

logger = logging.getLogger(__name__)

admin_router = APIRouter(prefix="/admin")
security = HTTPBearer()


async def verify_token(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
):
    """Verify the admin bearer token."""
    expected = getattr(request.app.state, "admin_token", None)
    if not expected or credentials.credentials != expected:
        raise HTTPException(status_code=401, detail="Invalid admin token")


# ── Health & Status ──────────────────────────────────────────────────


@admin_router.get("/health", dependencies=[Depends(verify_token)])
async def admin_health(request: Request):
    """Detailed health check — DB connectivity, watcher state."""
    db_ok = False
    db_latency = None

    if db.async_session_factory:
        try:
            t0 = datetime.now(UTC)
            async with db.async_session_factory() as s:
                await s.execute(text("SELECT 1"))
            dt = datetime.now(UTC) - t0
            db_latency = round(dt.total_seconds() * 1000, 1)
            db_ok = True
        except Exception as e:
            logger.warning("DB health check failed: %s", e)

    watcher_running = getattr(request.app.state, "watcher_task", None) is not None
    watcher_dir = request.app.state.config.watcher.root

    return {
        "database": {"connected": db_ok, "latency_ms": db_latency},
        "watcher": {"running": watcher_running, "directory": watcher_dir},
        "server": {"uptime_s": _uptime(request)},
    }


@admin_router.get("/status", dependencies=[Depends(verify_token)])
async def admin_status(request: Request):
    """Full system status — counts, watcher, config summary."""
    counts = {"indexed_files": 0, "sequences": 0, "features": 0, "primers": 0}

    if db.async_session_factory:
        try:
            async with db.async_session_factory() as s:
                counts["indexed_files"] = (await s.execute(
                    select(func.count()).select_from(IndexedFile)
                    .where(IndexedFile.status == "active")
                )).scalar()
                counts["sequences"] = (await s.execute(
                    select(func.count()).select_from(Sequence)
                )).scalar()
                counts["features"] = (await s.execute(
                    select(func.count()).select_from(Feature)
                )).scalar()
                counts["primers"] = (await s.execute(
                    select(func.count()).select_from(Primer)
                )).scalar()
        except Exception as e:
            logger.warning("Status query failed: %s", e)

    watcher_task = getattr(request.app.state, "watcher_task", None)

    return {
        "counts": counts,
        "database": getattr(request.app.state, "db_ready", False),
        "watcher": {
            "running": watcher_task is not None and not watcher_task.done(),
            "directory": request.app.state.config.watcher.root,
            "rules": len(request.app.state.config.watcher.rules),
        },
    }


# ── Watcher Control ─────────────────────────────────────────────────


@admin_router.post("/watcher/start", dependencies=[Depends(verify_token)])
async def watcher_start(request: Request):
    """Start the file watcher (scan + background watch)."""
    app = request.app

    if not getattr(app.state, "db_ready", False):
        raise HTTPException(status_code=503, detail="Database not available")

    task = getattr(app.state, "watcher_task", None)
    if task is not None and not task.done():
        return {"status": "already_running"}

    from hive.watcher.watcher import scan_and_ingest, watch_directory

    config = app.state.config.watcher
    count = await scan_and_ingest(config)

    stop_event = asyncio.Event()
    app.state.watcher_stop = stop_event
    app.state.watcher_task = asyncio.create_task(
        watch_directory(config, stop_event=stop_event)
    )

    return {"status": "started", "scanned": count}


@admin_router.post("/watcher/stop", dependencies=[Depends(verify_token)])
async def watcher_stop(request: Request):
    """Stop the file watcher."""
    app = request.app
    task = getattr(app.state, "watcher_task", None)

    if task is None or task.done():
        return {"status": "not_running"}

    stop = getattr(app.state, "watcher_stop", None)
    if stop:
        stop.set()
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    app.state.watcher_task = None
    app.state.watcher_stop = None
    logger.info("Watcher stopped via admin API")
    return {"status": "stopped"}


@admin_router.post("/watcher/rescan", dependencies=[Depends(verify_token)])
async def watcher_rescan(request: Request):
    """Force a full directory rescan (runs in background)."""
    if not getattr(request.app.state, "db_ready", False):
        raise HTTPException(status_code=503, detail="Database not available")

    from hive.watcher.watcher import scan_and_ingest

    config = request.app.state.config

    async def _run():
        try:
            count = await scan_and_ingest(config.watcher, blast_db_path=config.blast_dir)
            logger.info("Rescan complete: %d files indexed", count)
        except Exception as e:
            logger.error("Rescan failed: %s", e)

    asyncio.create_task(_run())
    return {"status": "started"}


@admin_router.post("/watcher/reindex", dependencies=[Depends(verify_token)])
async def watcher_reindex(request: Request):
    """Force full re-parse of all files (runs in background)."""
    if not getattr(request.app.state, "db_ready", False):
        raise HTTPException(status_code=503, detail="Database not available")

    from sqlalchemy import update

    # Reset all file hashes so ingest_file treats them as changed
    async with db.async_session_factory() as s:
        result = await s.execute(
            update(IndexedFile)
            .where(IndexedFile.status == "active")
            .values(file_hash="")
        )
        await s.commit()
        reset_count = result.rowcount

    logger.info("Reset %d file hashes for reindex", reset_count)

    from hive.watcher.watcher import scan_and_ingest

    config = request.app.state.config

    async def _run():
        try:
            count = await scan_and_ingest(config.watcher, blast_db_path=config.blast_dir)
            logger.info("Reindex complete: %d files re-parsed", count)
        except Exception as e:
            logger.error("Reindex failed: %s", e)

    asyncio.create_task(_run())
    return {"status": "started", "reset": reset_count}


# ── Database ─────────────────────────────────────────────────────────


@admin_router.get("/db/files", dependencies=[Depends(verify_token)])
async def db_files(request: Request):
    """List all indexed files."""
    if not getattr(request.app.state, "db_ready", False):
        raise HTTPException(status_code=503, detail="Database not available")

    async with db.async_session_factory() as s:
        rows = (await s.execute(
            select(
                IndexedFile.id,
                IndexedFile.file_path,
                IndexedFile.format,
                IndexedFile.status,
                IndexedFile.file_size,
                IndexedFile.indexed_at,
            ).order_by(IndexedFile.indexed_at.desc())
        )).all()

    return {
        "files": [
            {
                "id": r.id,
                "path": r.file_path,
                "format": r.format,
                "status": r.status,
                "size": r.file_size,
                "indexed_at": r.indexed_at.isoformat() if r.indexed_at else None,
            }
            for r in rows
        ]
    }


@admin_router.get("/db/errors", dependencies=[Depends(verify_token)])
async def db_errors(request: Request):
    """List files that failed to parse."""
    if not getattr(request.app.state, "db_ready", False):
        raise HTTPException(status_code=503, detail="Database not available")

    async with db.async_session_factory() as s:
        rows = (await s.execute(
            select(
                IndexedFile.file_path,
                IndexedFile.error_msg,
                IndexedFile.indexed_at,
            ).where(IndexedFile.status == "error")
        )).all()

    return {
        "errors": [
            {
                "path": r.file_path,
                "error": r.error_msg,
                "indexed_at": r.indexed_at.isoformat() if r.indexed_at else None,
            }
            for r in rows
        ]
    }


# ── Helpers ──────────────────────────────────────────────────────────


def _uptime(request: Request) -> float | None:
    started = getattr(request.app.state, "started_at", None)
    if started:
        return round((datetime.now(UTC) - started).total_seconds(), 1)
    return None
