"""Entry point — creates and runs the FastAPI application."""

from hive.config import load_config
from hive.server.app import create_app

config = load_config()
app = create_app(config)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "hive.main:app",
        host=config.server.host,
        port=config.server.port,
        reload=True,
    )
