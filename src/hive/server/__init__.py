"""Server package -- FastAPI app, REST routes, WebSocket handler."""

from hive.server.app import create_app

__all__ = ["create_app"]
