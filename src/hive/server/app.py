"""FastAPI application factory."""

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from hive.admin.routes import admin_router
from hive.admin.token import generate_token, save_token
from hive.chat.storage import ChatStorage
from hive.config import Settings
from hive.llm.pool import ModelPool
from hive.server.routes import router
from hive.server.websocket import ws_router
from hive.tools.factory import ToolFactory

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle — graceful when services unavailable."""
    config: Settings = app.state.config
    app.state.started_at = datetime.now(UTC)
    app.state.db_ready = False

    # --- Admin token ---
    token = generate_token()
    app.state.admin_token = token
    save_token(token)
    logger.info("Admin token: %s", token)

    # --- Chat storage ---
    app.state.chat_storage = ChatStorage(config.chats_dir)

    # --- Database ---
    try:
        from hive.db.session import init_db
        app.state.db_ready = await init_db(config.database)
    except Exception as e:
        logger.warning("Database init skipped: %s", e)

    # --- Model pool ---
    pool = ModelPool(config.llm.models)
    app.state.model_pool = pool
    default_client = pool.get(pool.default_id) if pool.default_id else None
    if default_client:
        try:
            if await default_client.health():
                logger.info("LLM connected: %s", pool.default_id)
            else:
                logger.warning("Default LLM not available: %s", pool.default_id)
        except Exception:
            logger.warning("Default LLM not available: %s", pool.default_id)

    # --- Tool registry ---
    app.state.tool_registry = ToolFactory.discover(config)
    logger.info("Tool registry: %d tools", len(app.state.tool_registry.all()))

    # --- File watcher (only if DB is available) ---
    app.state.watcher_task = None
    app.state.watcher_stop = None

    if app.state.db_ready and config.watcher.rules:
        from hive.watcher.watcher import scan_and_ingest, watch_directory

        async def _scan_then_watch():
            try:
                count = await scan_and_ingest(config.watcher, blast_db_path=config.blast_dir)
                logger.info("Initial scan indexed %d files", count)
            except Exception as e:
                logger.warning("Initial scan failed: %s", e)

            # Always rebuild BLAST index after scan (covers restart with no new files)
            try:
                from hive.tools.blast import build_blast_index
                await build_blast_index(config.blast_dir)
            except Exception as e:
                logger.warning("BLAST index build failed: %s", e)

            stop_event = asyncio.Event()
            app.state.watcher_stop = stop_event
            await watch_directory(
                config.watcher,
                stop_event=stop_event,
                blast_db_path=config.blast_dir,
            )

        app.state.watcher_task = asyncio.create_task(_scan_then_watch())

    yield

    # --- Shutdown ---
    task = app.state.watcher_task
    if task and not task.done():
        stop = app.state.watcher_stop
        if stop:
            stop.set()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        logger.info("File watcher stopped")

    # ModelPool clients are stateless (litellm manages connections)


def create_app(config: Settings) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Hive Browser",
        description="Lab sequence search platform",
        lifespan=lifespan,
    )

    app.state.config = config

    app.include_router(router)
    app.include_router(ws_router)
    app.include_router(admin_router)

    static_dir = Path("static")
    if static_dir.exists():
        app.mount("/", StaticFiles(directory="static", html=True), name="static")

    return app
