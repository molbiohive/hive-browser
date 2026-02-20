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


@router.get("/models")
async def list_models(request: Request):
    """Return configured models + optionally auto-discovered Ollama models."""
    config = getattr(request.app.state, "config", None)
    pool = getattr(request.app.state, "model_pool", None)
    configured = [
        {"id": m.id, "provider": m.provider, "model": m.model}
        for m in pool.entries()
    ] if pool else []

    discovered = []
    if config and config.llm.auto_discover and pool:
        ollama_base = next(
            (m.base_url for m in pool.entries() if m.provider == "ollama"), None
        )
        if ollama_base:
            discovered = await _discover_ollama(ollama_base, configured)

    return {"configured": configured, "ollama": discovered}


async def _discover_ollama(base_url: str, configured: list[dict]) -> list[dict]:
    """Fetch available models from Ollama API, excluding already-configured ones."""
    import httpx

    url = base_url.rstrip("/v1").rstrip("/") + "/api/tags"
    configured_ids = {m["id"] for m in configured}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return [
                    {"id": f"ollama/{m['name']}", "provider": "ollama", "model": m["name"]}
                    for m in resp.json().get("models", [])
                    if f"ollama/{m['name']}" not in configured_ids
                ]
    except Exception as e:
        logger.warning("Ollama discovery failed: %s", e)
    return []


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
