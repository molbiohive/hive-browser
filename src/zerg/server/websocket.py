"""WebSocket handler for concurrent chat sessions."""

import logging
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from zerg.tools.router import route_input

logger = logging.getLogger(__name__)

ws_router = APIRouter()


class ConnectionManager:
    """Manages concurrent WebSocket connections."""

    def __init__(self):
        self.active: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket) -> str:
        await websocket.accept()
        conn_id = str(uuid4())
        self.active[conn_id] = websocket
        logger.info("Client connected: %s (total: %d)", conn_id, len(self.active))
        return conn_id

    def disconnect(self, conn_id: str):
        self.active.pop(conn_id, None)
        logger.info("Client disconnected: %s (total: %d)", conn_id, len(self.active))

    async def send_json(self, conn_id: str, data: dict):
        if ws := self.active.get(conn_id):
            await ws.send_json(data)


manager = ConnectionManager()


@ws_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    conn_id = await manager.connect(websocket)

    # Get registry and LLM client from app state
    app = websocket.app
    registry = getattr(app.state, "tool_registry", None)
    llm_client = getattr(app.state, "llm_client", None)

    try:
        while True:
            data = await websocket.receive_json()
            content = data.get("content", "").strip()

            if not content:
                continue

            if not registry:
                await manager.send_json(conn_id, {
                    "type": "message",
                    "content": "Server not ready — tool registry not initialized.",
                })
                continue

            # Route through the orchestrator
            result = await route_input(
                user_input=content,
                registry=registry,
                llm_client=llm_client,
            )

            # Send response back to client
            response = {"type": "message", "content": result.get("content", "")}

            # Attach widget data if tool produced structured output
            if result.get("type") == "tool_result" and result.get("data"):
                tool_name = result["tool"]
                response["widget"] = {
                    "type": _widget_type(tool_name),
                    "tool": tool_name,
                    "params": {},
                    "data": result["data"],
                }

            await manager.send_json(conn_id, response)

    except WebSocketDisconnect:
        manager.disconnect(conn_id)


def _widget_type(tool_name: str) -> str:
    """Map tool name to frontend widget type."""
    return {
        "search": "table",
        "blast": "blast",
        "profile": "profile",
        "browse": "table",
        "status": "profile",
    }.get(tool_name, "text")
