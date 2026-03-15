"""Async database session management."""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from hive.config import DatabaseConfig

logger = logging.getLogger(__name__)

engine = None
async_session_factory = None


async def init_db(config: DatabaseConfig) -> bool:
    """Initialize the async database engine and session factory.

    Returns True if the database is reachable, False otherwise.
    The engine/factory are always created (for later reconnection).
    """
    global engine, async_session_factory

    engine = create_async_engine(config.url, echo=False)
    async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        logger.info("Database connected, pg_trgm extension ready")
        return True
    except Exception as e:
        logger.warning("Database not available: %s", e)
        return False


