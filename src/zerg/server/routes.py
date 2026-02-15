"""REST API endpoints."""

import logging

from fastapi import APIRouter
from sqlalchemy import func, select

from zerg.db import session as db
from zerg.db.models import Feature, IndexedFile, Primer, Sequence

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


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
