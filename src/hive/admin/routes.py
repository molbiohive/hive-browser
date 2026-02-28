"""Admin API endpoints — protected by bearer token."""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select, text

from hive.db import session as db
from hive.db.models import Feature, IndexedFile, Primer, Sequence
from hive.ps import ProcessState

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

    ps = getattr(request.app.state, "ps", None)
    watcher_state = ps.get_state("watcher") if ps else None
    watcher_dir = request.app.state.config.watcher.root

    return {
        "database": {"connected": db_ok, "latency_ms": db_latency},
        "watcher": {
            "state": watcher_state.value if watcher_state else "unknown",
            "directory": watcher_dir,
        },
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

    ps = getattr(request.app.state, "ps", None)
    watcher_state = ps.get_state("watcher") if ps else None

    return {
        "counts": counts,
        "database": getattr(request.app.state, "db_ready", False),
        "watcher": {
            "state": watcher_state.value if watcher_state else "unknown",
            "directory": request.app.state.config.watcher.root,
            "rules": len(request.app.state.config.watcher.rules),
        },
    }


# ── Process Control ─────────────────────────────────────────────────


def _get_ps(request: Request):
    ps = getattr(request.app.state, "ps", None)
    if not ps:
        raise HTTPException(status_code=503, detail="Process registry not available")
    return ps


@admin_router.get("/ps", dependencies=[Depends(verify_token)])
async def ps_list(request: Request):
    """List all registered processes and their states."""
    return {"processes": _get_ps(request).status()}


@admin_router.post("/ps/{name}/start", dependencies=[Depends(verify_token)])
async def ps_start(name: str, request: Request):
    """Start a registered process."""
    ps = _get_ps(request)
    state = ps.get_state(name)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Unknown process: {name}")
    if state == ProcessState.running:
        return {"status": "already_running", "name": name}
    await ps.start(name)
    return {"status": "started", "name": name}


@admin_router.post("/ps/{name}/stop", dependencies=[Depends(verify_token)])
async def ps_stop(name: str, request: Request):
    """Stop a running process."""
    ps = _get_ps(request)
    state = ps.get_state(name)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Unknown process: {name}")
    if state not in (ProcessState.running, ProcessState.paused):
        return {"status": "not_running", "name": name}
    await ps.stop(name)
    return {"status": "stopped", "name": name}


@admin_router.post("/ps/{name}/pause", dependencies=[Depends(verify_token)])
async def ps_pause(name: str, request: Request):
    """Pause a running process."""
    ps = _get_ps(request)
    state = ps.get_state(name)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Unknown process: {name}")
    if state != ProcessState.running:
        return {"status": "not_running", "name": name}
    ps.pause(name)
    return {"status": "paused", "name": name}


@admin_router.post("/ps/{name}/resume", dependencies=[Depends(verify_token)])
async def ps_resume(name: str, request: Request):
    """Resume a paused process."""
    ps = _get_ps(request)
    state = ps.get_state(name)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Unknown process: {name}")
    if state != ProcessState.paused:
        return {"status": "not_paused", "name": name}
    ps.resume(name)
    return {"status": "resumed", "name": name}


# ── Database ─────────────────────────────────────────────────────────



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


# ── DB Audit/Cleanup ─────────────────────────────────────────────────


@admin_router.post("/db/audit", dependencies=[Depends(verify_token)])
async def db_audit(request: Request, body: dict | None = None):
    """Audit database integrity — counts, duplicates, orphans."""
    if not getattr(request.app.state, "db_ready", False):
        raise HTTPException(status_code=503, detail="Database not available")

    from hive.admin.db import audit

    verbose = (body or {}).get("verbose", False)
    watcher_root = request.app.state.config.watcher.root
    async with db.async_session_factory() as s:
        return await audit(s, watcher_root, verbose=verbose)


@admin_router.post("/db/dedupe", dependencies=[Depends(verify_token)])
async def db_dedupe(request: Request, body: dict | None = None):
    """Remove duplicate IndexedFile records (same file_hash)."""
    if not getattr(request.app.state, "db_ready", False):
        raise HTTPException(status_code=503, detail="Database not available")

    from hive.admin.db import dedupe

    dry_run = (body or {}).get("dry_run", True)
    async with db.async_session_factory() as s:
        return await dedupe(s, dry_run=dry_run)


@admin_router.post("/db/prune", dependencies=[Depends(verify_token)])
async def db_prune(request: Request, body: dict | None = None):
    """Remove IndexedFile records for files that no longer exist on disk."""
    if not getattr(request.app.state, "db_ready", False):
        raise HTTPException(status_code=503, detail="Database not available")

    from hive.admin.db import prune

    params = body or {}
    dry_run = params.get("dry_run", True)
    no_archive = params.get("no_archive", False)
    config = request.app.state.config
    watcher_root = config.watcher.root
    archive_dir = str(Path(config.data_root).expanduser() / "archive")

    async with db.async_session_factory() as s:
        return await prune(
            s, watcher_root, archive_dir=archive_dir,
            dry_run=dry_run, no_archive=no_archive,
        )


# ── Helpers ──────────────────────────────────────────────────────────


def _uptime(request: Request) -> float | None:
    started = getattr(request.app.state, "started_at", None)
    if started:
        return round((datetime.now(UTC) - started).total_seconds(), 1)
    return None
