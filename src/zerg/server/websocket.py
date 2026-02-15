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
        self.histories: dict[str, list[dict]] = {}

    async def connect(self, websocket: WebSocket) -> str:
        await websocket.accept()
        conn_id = str(uuid4())
        self.active[conn_id] = websocket
        self.histories[conn_id] = []
        logger.info("Client connected: %s (total: %d)", conn_id, len(self.active))
        return conn_id

    def disconnect(self, conn_id: str):
        self.active.pop(conn_id, None)
        self.histories.pop(conn_id, None)
        logger.info("Client disconnected: %s (total: %d)", conn_id, len(self.active))

    async def send_json(self, conn_id: str, data: dict):
        if ws := self.active.get(conn_id):
            await ws.send_json(data)

    def append_history(self, conn_id: str, role: str, content: str, max_pairs: int = 20):
        history = self.histories.get(conn_id)
        if history is None:
            return
        history.append({"role": role, "content": content})
        max_msgs = max_pairs * 2
        if len(history) > max_msgs:
            self.histories[conn_id] = history[-max_msgs:]

    def get_history(self, conn_id: str) -> list[dict]:
        return self.histories.get(conn_id, [])


manager = ConnectionManager()


@ws_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    conn_id = await manager.connect(websocket)

    # Get registry, LLM client, and config from app state
    app = websocket.app
    config = getattr(app.state, "config", None)
    registry = getattr(app.state, "tool_registry", None)
    llm_client = getattr(app.state, "llm_client", None)
    max_pairs = config.chat.max_history_pairs if config else 20

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

            # Track user message in history
            manager.append_history(conn_id, "user", content, max_pairs)

            # Route through the orchestrator with conversation history
            result = await route_input(
                user_input=content,
                registry=registry,
                llm_client=llm_client,
                history=manager.get_history(conn_id)[:-1],  # exclude current msg (router adds it)
            )

            # Track assistant response in history
            assistant_content = result.get("content", "")
            if assistant_content:
                manager.append_history(conn_id, "assistant", assistant_content, max_pairs)

            # Send response back to client
            response = {"type": "message", "content": assistant_content}

            # Attach widget data if tool produced structured output
            if result.get("type") == "tool_result" and result.get("data"):
                tool_name = result["tool"]
                response["widget"] = {
                    "type": _widget_type(tool_name),
                    "tool": tool_name,
                    "params": {},
                    "data": result["data"],
                }
            elif result.get("type") == "form":
                response["widget"] = {
                    "type": "form",
                    "tool": result["tool"],
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
        "status": "status",
    }.get(tool_name, "text")
