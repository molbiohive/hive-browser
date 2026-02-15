"""FastAPI application factory."""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from zerg.admin.routes import admin_router
from zerg.admin.token import generate_token, save_token
from zerg.chat.storage import ChatStorage
from zerg.config import Settings
from zerg.llm.client import LLMClient
from zerg.server.routes import router
from zerg.server.websocket import ws_router
from zerg.tools.base import ToolRegistry
from zerg.tools.blast import BlastTool, build_blast_index
from zerg.tools.browse import BrowseTool
from zerg.tools.profile import ProfileTool
from zerg.tools.search import SearchTool
from zerg.tools.status import StatusTool

logger = logging.getLogger(__name__)


def _build_registry(config: Settings, llm_client: LLMClient | None) -> ToolRegistry:
    """Create and populate the tool registry."""
    registry = ToolRegistry()
    registry.register(SearchTool())
    registry.register(BlastTool(db_path=config.blast.db_path, binary=config.blast.binary))
    registry.register(ProfileTool())
    registry.register(BrowseTool(watch_root=config.watcher.root))
    registry.register(StatusTool(llm_client=llm_client))
    return registry


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle — graceful when services unavailable."""
    config: Settings = app.state.config
    app.state.started_at = datetime.now(timezone.utc)
    app.state.db_ready = False

    # --- Admin token ---
    token = generate_token()
    app.state.admin_token = token
    save_token(token)
    logger.info("Admin token: %s", token)

    # --- Chat storage ---
    app.state.chat_storage = ChatStorage(config.chat.storage_dir)

    # --- Database ---
    try:
        from zerg.db.session import init_db
        app.state.db_ready = await init_db(config.database)
    except Exception as e:
        logger.warning("Database init skipped: %s", e)

    # --- LLM client ---
    llm_client = LLMClient(config.llm)
    app.state.llm_client = llm_client
    try:
        if await llm_client.health():
            logger.info("LLM connected: %s", config.llm.model)
        else:
            logger.warning("LLM not available at %s", config.llm.base_url)
            app.state.llm_client = None
    except Exception:
        logger.warning("LLM not available at %s", config.llm.base_url)
        app.state.llm_client = None

    # --- Tool registry ---
    app.state.tool_registry = _build_registry(config, app.state.llm_client)
    logger.info("Tool registry: %d tools", len(app.state.tool_registry.all()))

    # --- File watcher (only if DB is available) ---
    app.state.watcher_task = None
    app.state.watcher_stop = None

    if app.state.db_ready and config.watcher.rules:
        from zerg.watcher.watcher import scan_and_ingest, watch_directory

        try:
            count = await scan_and_ingest(config.watcher)
            logger.info("Initial scan indexed %d files", count)
        except Exception as e:
            logger.warning("Initial scan failed: %s", e)

        stop_event = asyncio.Event()
        app.state.watcher_stop = stop_event
        app.state.watcher_task = asyncio.create_task(
            watch_directory(config.watcher, stop_event=stop_event)
        )

    # --- BLAST index ---
    if app.state.db_ready:
        try:
            await build_blast_index(config.blast.db_path)
        except Exception as e:
            logger.warning("BLAST index build failed: %s", e)

    yield

    # --- Shutdown ---
    task = app.state.watcher_task
    if task and not task.done():
        stop = app.state.watcher_stop
        if stop:
            stop.set()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        logger.info("File watcher stopped")

    if llm_client:
        await llm_client.close()


def create_app(config: Settings) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Zerg Browser",
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
