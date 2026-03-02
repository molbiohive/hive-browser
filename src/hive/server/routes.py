"""REST API endpoints."""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from hive.db import session as db
from hive.db.models import IndexedFile, Part, PartInstance, Sequence
from hive.users.service import (
    create_user,
    get_user_by_slug,
    get_user_by_token,
    list_users,
    validate_username,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


# ── User endpoints ────────────────────────────────────────


@router.post("/users")
async def create_user_endpoint(request: Request):
    body = await request.json()
    username = body.get("username", "").strip()
    if not validate_username(username):
        return JSONResponse(
            {"error": "Invalid username: ASCII letters, digits, hyphens,"
             " underscores, spaces (1-50 chars)"},
            status_code=422,
        )
    if not db.async_session_factory:
        return JSONResponse({"error": "Database not available"}, status_code=503)
    try:
        async with db.async_session_factory() as s:
            user = await create_user(s, username)
            await s.commit()
            return {
                "id": user.id, "username": user.username,
                "slug": user.slug, "token": user.token,
            }
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=409)


@router.get("/users")
async def list_users_endpoint():
    if not db.async_session_factory:
        return []
    async with db.async_session_factory() as s:
        users = await list_users(s)
        return [{"id": u.id, "username": u.username, "slug": u.slug} for u in users]


@router.post("/users/login")
async def login_user(request: Request):
    """Passwordless login by slug (local server, no passwords)."""
    body = await request.json()
    slug = body.get("slug", "").strip()
    if not slug or not db.async_session_factory:
        return JSONResponse({"error": "Invalid request"}, status_code=400)
    async with db.async_session_factory() as s:
        user = await get_user_by_slug(s, slug)
        if not user:
            return JSONResponse({"error": "User not found"}, status_code=404)
        return {
            "id": user.id, "username": user.username,
            "slug": user.slug, "token": user.token,
        }


@router.get("/users/me")
async def get_current_user(request: Request):
    token = request.cookies.get("hive_token")
    if not token or not db.async_session_factory:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    async with db.async_session_factory() as s:
        user = await get_user_by_token(s, token)
        if not user:
            return JSONResponse({"error": "Invalid token"}, status_code=401)
        return {
            "id": user.id,
            "username": user.username,
            "slug": user.slug,
            "preferences": user.preferences,
        }


# ── Chat endpoints ────────────────────────────────────────


async def _get_user_slug(request: Request) -> str | None:
    """Extract user slug from hive_token cookie."""
    token = request.cookies.get("hive_token")
    if not token or not db.async_session_factory:
        return None
    async with db.async_session_factory() as s:
        user = await get_user_by_token(s, token)
        return user.slug if user else None


@router.get("/chats")
async def list_chats(request: Request):
    storage = getattr(request.app.state, "chat_storage", None)
    if not storage:
        return []
    slug = await _get_user_slug(request)
    return storage.list_chats(slug)


@router.get("/chats/{chat_id}")
async def get_chat(chat_id: str, request: Request):
    storage = getattr(request.app.state, "chat_storage", None)
    if not storage:
        return {"error": "Chat storage not available"}
    slug = await _get_user_slug(request)
    data = storage.load(chat_id, slug)
    if not data:
        return {"error": "Chat not found"}
    return data


@router.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str, request: Request):
    storage = getattr(request.app.state, "chat_storage", None)
    if not storage:
        return {"error": "Chat storage not available"}
    slug = await _get_user_slug(request)
    deleted = storage.delete(chat_id, slug)
    return {"deleted": deleted}



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


# ── Search / BLAST endpoints (for search panel) ──────────


@router.get("/search")
async def search_endpoint(request: Request, q: str = ""):
    """Direct pg_trgm search -- reuses SearchTool.execute()."""
    registry = getattr(request.app.state, "tool_registry", None)
    tool = registry.get("search") if registry else None
    if not tool:
        return JSONResponse({"error": "Search tool not available"}, status_code=503)
    result = await tool.execute({"query": q}, mode="direct")
    return result


@router.post("/blast")
async def blast_endpoint(request: Request):
    """Direct BLAST search -- reuses BlastTool.execute()."""
    registry = getattr(request.app.state, "tool_registry", None)
    tool = registry.get("blast") if registry else None
    if not tool:
        return JSONResponse({"error": "BLAST tool not available"}, status_code=503)
    body = await request.json()
    sequence = body.get("sequence", "").strip()
    if not sequence:
        return JSONResponse({"error": "Missing required field: sequence"}, status_code=422)
    params = {"sequence": sequence}
    if program := body.get("program"):
        params["program"] = program
    result = await tool.execute(params, mode="direct")
    return result


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
            "parts": 0,
            "part_instances": 0,
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
            parts = (await s.execute(
                select(func.count()).select_from(Part)
            )).scalar()
            pis = (await s.execute(
                select(func.count()).select_from(PartInstance)
            )).scalar()

        return {
            "indexed_files": files,
            "sequences": seqs,
            "parts": parts,
            "part_instances": pis,
            "database": True,
        }
    except Exception as e:
        logger.warning("Status query failed: %s", e)
        return {
            "indexed_files": 0,
            "sequences": 0,
            "parts": 0,
            "part_instances": 0,
            "database": False,
        }
