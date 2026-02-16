"""REST API endpoints."""

import logging
import platform
import subprocess
from pathlib import Path

from fastapi import APIRouter, Request
from sqlalchemy import func, select

from zerg.db import session as db
from zerg.db.models import Feature, IndexedFile, Primer, Sequence

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


# ── Chat endpoints ────────────────────────────────────────


@router.get("/chats")
async def list_chats(request: Request):
    storage = getattr(request.app.state, "chat_storage", None)
    if not storage:
        return []
    return storage.list_chats()


@router.get("/chats/{chat_id}")
async def get_chat(chat_id: str, request: Request):
    storage = getattr(request.app.state, "chat_storage", None)
    if not storage:
        return {"error": "Chat storage not available"}
    data = storage.load(chat_id)
    if not data:
        return {"error": "Chat not found"}
    return data


@router.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str, request: Request):
    storage = getattr(request.app.state, "chat_storage", None)
    if not storage:
        return {"error": "Chat storage not available"}
    deleted = storage.delete(chat_id)
    return {"deleted": deleted}


@router.post("/open-file")
async def open_file(request: Request):
    """Open a file's parent directory in the OS file manager."""
    body = await request.json()
    file_path = body.get("path", "")

    if not file_path:
        return {"error": "No file path provided"}

    path = Path(file_path)
    if not path.exists():
        return {"error": f"File not found: {file_path}"}

    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.Popen(["open", "-R", str(path)])
        elif system == "Linux":
            subprocess.Popen(["xdg-open", str(path.parent)])
        else:
            return {"error": f"Unsupported platform: {system}"}
    except Exception as e:
        return {"error": str(e)}

    return {"status": "ok", "path": str(path)}


@router.get("/health")
async def health():
    """Health check for container orchestration."""
    db_ok = False
    if db.async_session_factory:
        try:
            async with db.async_session_factory() as s:
                await s.execute(select(func.count()).select_from(IndexedFile))
            db_ok = True
        except Exception:
            pass

    return {
        "status": "healthy" if db_ok else "degraded",
        "checks": {"database": db_ok},
    }


@router.get("/status")
async def status():
    """System status — indexed files, DB health, LLM status."""
    if not db.async_session_factory:
        return {
            "indexed_files": 0,
            "sequences": 0,
            "features": 0,
            "primers": 0,
            "database": False,
        }

    try:
        async with db.async_session_factory() as s:
            files = (await s.execute(
                select(func.count()).select_from(IndexedFile).where(IndexedFile.status == "active")
            )).scalar()
            seqs = (await s.execute(
                select(func.count()).select_from(Sequence)
            )).scalar()
            feats = (await s.execute(
                select(func.count()).select_from(Feature)
            )).scalar()
            prims = (await s.execute(
                select(func.count()).select_from(Primer)
            )).scalar()

        return {
            "indexed_files": files,
            "sequences": seqs,
            "features": feats,
            "primers": prims,
            "database": True,
        }
    except Exception as e:
        logger.warning("Status query failed: %s", e)
        return {
            "indexed_files": 0,
            "sequences": 0,
            "features": 0,
            "primers": 0,
            "database": False,
        }
