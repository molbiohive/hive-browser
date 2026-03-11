"""FastAPI application factory."""

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
from hive.deps import DepRegistry
from hive.deps.blast import BlastDep
from hive.deps.mafft import MafftDep
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
    logger.debug("Admin token: %s", token)

    # --- Chat storage ---
    app.state.chat_storage = ChatStorage(config.chats_dir)

    # --- Database ---
    try:
        from hive.db.session import init_db
        app.state.db_ready = await init_db(config.database)
    except Exception as e:
        logger.warning("Database init skipped: %s", e)

    # --- Bootstrap enzymes ---
    if app.state.db_ready:
        try:
            from hive.cloning.enzymes import bootstrap_enzymes
            from hive.db.session import async_session_factory

            async with async_session_factory() as session:
                await bootstrap_enzymes(session)
                await session.commit()
        except Exception as e:
            logger.warning("Enzyme bootstrap failed: %s", e)

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

    # --- Dep registry ---
    dep_registry = DepRegistry()
    dep_registry.register(BlastDep(config.dep_data_dir("blast"), config.deps.blast.bin_dir))
    dep_registry.register(MafftDep(config.deps.mafft.bin_dir))
    app.state.dep_registry = dep_registry

    # --- Tool registry (with quarantine for external tools) ---
    approved_files: set[str] = set()
    if app.state.db_ready:
        from hive.tools.quarantine import sync_quarantine
        approved_files = await sync_quarantine(config.tools_dir)
    app.state.tool_registry = ToolFactory.discover(
        config, approved_files=approved_files
    )
    logger.info("Tool registry: %d tools", len(app.state.tool_registry.all()))

    # --- Tool RAG (planning + selection) ---
    app.state.tool_rag = None
    if config.llm.tool_rag_enabled:
        from hive.llm.tool_rag import ToolRAG

        llm_tools = app.state.tool_registry.llm_tools()
        if llm_tools:
            app.state.tool_rag = ToolRAG(
                tools=llm_tools,
                embedding_model=config.llm.tool_rag_model,
                embedding_base_url=config.llm.tool_rag_base_url,
                threshold=config.llm.tool_rag_threshold,
                top_k=config.llm.tool_rag_top_k,
            )

    # --- Process registry ---
    from hive.ps import ProcessRegistry
    from hive.ps.match import MatchProcess
    from hive.ps.scan import ReindexProcess, RescanProcess, ScanProcess
    from hive.ps.watcher import WatcherProcess

    ps = ProcessRegistry()
    ps.register(ScanProcess(config.watcher, config.data_root, dep_registry))
    ps.register(WatcherProcess(config.watcher, dep_registry))
    ps.register(RescanProcess(config.watcher, config.data_root, dep_registry))
    ps.register(ReindexProcess(config.watcher, config.data_root, dep_registry))
    ps.register(MatchProcess(config, dep_registry))
    app.state.ps = ps

    if app.state.db_ready and config.watcher.rules:
        try:
            await ps.start("scan")
            # Wait for scan to finish
            task = ps._tasks.get("scan")
            if task:
                await task
        except Exception as e:
            logger.warning("Initial scan failed: %s", e)

        try:
            await dep_registry.setup_all()
        except Exception as e:
            logger.warning("Dep setup failed: %s", e)

        await ps.start("watcher")

    yield

    # --- Shutdown ---
    await ps.stop_all()

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
