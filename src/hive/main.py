"""Entry point — creates and runs the FastAPI application."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from hive.config import Settings, load_config
from hive.server.app import create_app


def init_logging(config: Settings) -> None:
    """Configure centralized logging with file output and optional LLM dump."""
    log_dir = Path(config.logs_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, config.logging.level.upper(), logging.INFO)
    fmt = "%(asctime)s %(levelname)-5s %(name)s: %(message)s"

    root = logging.getLogger("hive")
    root.setLevel(level)

    # Console
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(fmt))
    root.addHandler(console)

    # File — hive.log, 10MB x 5
    fh = RotatingFileHandler(log_dir / "hive.log", maxBytes=10_000_000, backupCount=5)
    fh.setFormatter(logging.Formatter(fmt))
    root.addHandler(fh)

    # LLM dump — llm.jsonl, 50MB x 3
    if config.logging.llm_dump:
        llm_logger = logging.getLogger("hive.llm.dump")
        llm_handler = RotatingFileHandler(
            log_dir / "llm.jsonl", maxBytes=50_000_000, backupCount=3
        )
        llm_handler.setFormatter(logging.Formatter("%(message)s"))
        llm_logger.addHandler(llm_handler)
        llm_logger.setLevel(logging.DEBUG)
        llm_logger.propagate = False  # don't echo to hive.log


config = load_config()
init_logging(config)
app = create_app(config)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "hive.main:app",
        host=config.server.host,
        port=config.server.port,
        reload=True,
    )
