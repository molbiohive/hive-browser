"""Entry point — creates and runs the FastAPI application."""

from zerg.config import load_config
from zerg.server.app import create_app

config = load_config()
app = create_app(config)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "zerg.main:app",
        host=config.server.host,
        port=config.server.port,
        reload=True,
    )
