"""WebSocket handler for concurrent chat sessions."""

import logging
from datetime import datetime, timezone
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

    def count_user_messages(self, conn_id: str) -> int:
        return sum(1 for m in self.histories.get(conn_id, []) if m["role"] == "user")


manager = ConnectionManager()


@ws_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    conn_id = await manager.connect(websocket)

    # Get services from app state
    app = websocket.app
    config = getattr(app.state, "config", None)
    registry = getattr(app.state, "tool_registry", None)
    llm_client = getattr(app.state, "llm_client", None)
    chat_storage = getattr(app.state, "chat_storage", None)
    max_pairs = config.chat.max_history_pairs if config else 20
    save_threshold = config.chat.auto_save_after if config else 2

    # Send config to frontend on connect
    await manager.send_json(conn_id, {
        "type": "init",
        "config": {
            "search_columns": config.search.columns if config else ["name", "size_bp", "topology", "features"],
            "max_history_pairs": max_pairs,
        },
    })

    # Per-connection chat tracking
    chat_id = None
    chat_messages: list[dict] = []
    title_generated = False

    try:
        while True:
            data = await websocket.receive_json()

            # Handle chat resume
            if data.get("type") == "load_chat" and chat_storage:
                requested_id = data.get("chatId")
                if requested_id:
                    saved = chat_storage.load(requested_id)
                    if saved:
                        chat_id = requested_id
                        chat_messages = saved.get("messages", [])
                        title_generated = bool(saved.get("title"))
                        # Rebuild LLM history from saved messages
                        manager.histories[conn_id] = [
                            {"role": m["role"], "content": m["content"]}
                            for m in chat_messages
                        ]
                        await manager.send_json(conn_id, {
                            "type": "chat_loaded",
                            "chatId": chat_id,
                            "messages": chat_messages,
                            "title": saved.get("title"),
                        })
                continue

            content = data.get("content", "").strip()
            if not content:
                continue

            if not registry:
                await manager.send_json(conn_id, {
                    "type": "message",
                    "content": "Server not ready — tool registry not initialized.",
                })
                continue

            # Track user message
            manager.append_history(conn_id, "user", content, max_pairs)
            chat_messages.append({"role": "user", "content": content, "ts": _now_iso()})

            # Route through the orchestrator
            result = await route_input(
                user_input=content,
                registry=registry,
                llm_client=llm_client,
                history=manager.get_history(conn_id)[:-1],
            )

            # Track assistant response
            assistant_content = result.get("content", "")
            if assistant_content:
                manager.append_history(conn_id, "assistant", assistant_content, max_pairs)

            # Build response
            response = {"type": "message", "content": assistant_content}

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

            # Save assistant message
            assistant_msg: dict = {"role": "assistant", "content": assistant_content, "ts": _now_iso()}
            if response.get("widget"):
                assistant_msg["widget"] = response["widget"]
            chat_messages.append(assistant_msg)

            await manager.send_json(conn_id, response)

            # Auto-save chat after threshold
            if chat_storage and manager.count_user_messages(conn_id) >= save_threshold:
                if chat_id is None:
                    chat_id = chat_storage.new_chat_id()
                chat_storage.save(chat_id, chat_messages)

                # Generate title once via LLM
                if not title_generated and llm_client:
                    title_generated = True
                    title = await _generate_chat_title(llm_client, chat_messages[:4])
                    if title:
                        chat_storage.update_title(chat_id, title)
                        await manager.send_json(conn_id, {
                            "type": "chat_saved",
                            "chatId": chat_id,
                            "title": title,
                        })

    except WebSocketDisconnect:
        manager.disconnect(conn_id)


async def _generate_chat_title(llm_client, messages: list[dict]) -> str | None:
    """Ask LLM to generate a short chat title from the first few messages."""
    try:
        summary_input = "\n".join(f"{m['role']}: {m['content'][:200]}" for m in messages)
        resp = await llm_client.chat([
            {"role": "system", "content": "Generate a very short title (3-6 words) for this chat. Reply with ONLY the title, no quotes."},
            {"role": "user", "content": summary_input},
        ])
        title = resp["choices"][0]["message"].get("content", "").strip().strip('"\'')
        return title[:60] if title else None
    except Exception as e:
        logger.warning("Failed to generate chat title: %s", e)
        return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _widget_type(tool_name: str) -> str:
    """Map tool name to frontend widget type."""
    return {
        "search": "table",
        "blast": "blast",
        "profile": "profile",
        "browse": "table",
        "status": "status",
    }.get(tool_name, "text")
