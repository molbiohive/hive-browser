"""Async database session management."""

import logging
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from zerg.config import DatabaseConfig

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


async def create_tables():
    """Create all tables from models (for dev/testing — use Alembic in production)."""
    from zerg.db.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Tables created")


async def drop_tables():
    """Drop all tables (for testing only)."""
    from zerg.db.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    logger.info("Tables dropped")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session for dependency injection."""
    async with async_session_factory() as session:
        yield session
