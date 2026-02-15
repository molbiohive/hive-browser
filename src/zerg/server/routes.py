"""REST API endpoints."""

import logging

from fastapi import APIRouter, Request
from sqlalchemy import func, select

from zerg.db import session as db
from zerg.db.models import Feature, IndexedFile, Primer, Sequence

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


# ── Frontend config ────────────────────────────────────────


@router.get("/config")
async def frontend_config(request: Request):
    """Expose relevant config to frontend."""
    config = getattr(request.app.state, "config", None)
    if not config:
        return {}
    return {
        "search_columns": config.search.columns,
        "max_history_pairs": config.chat.max_history_pairs,
    }


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
