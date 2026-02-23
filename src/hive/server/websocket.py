"""WebSocket handler for concurrent chat sessions."""

import asyncio
import contextlib
import json
import logging
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import func, select

from hive.db import session as db
from hive.db.models import Feature, IndexedFile, Sequence, User
from hive.tools.router import route_input
from hive.users.service import create_feedback, get_user_by_token, update_preferences

logger = logging.getLogger(__name__)

ws_router = APIRouter()


class ConnectionManager:
    """Manages concurrent WebSocket connections."""

    def __init__(self):
        self.active: dict[str, WebSocket] = {}
        self.histories: dict[str, list[dict]] = {}
        self.tasks: dict[str, asyncio.Task] = {}

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
        task = self.tasks.pop(conn_id, None)
        if task and not task.done():
            task.cancel()
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

    # --- Authenticate via token query param ---
    token = websocket.query_params.get("token")
    user = None
    if token and db.async_session_factory:
        async with db.async_session_factory() as s:
            user = await get_user_by_token(s, token)
    if not user:
        await websocket.close(code=4001, reason="auth_required")
        manager.disconnect(conn_id)
        return

    user_slug = user.slug

    # Get services from app state
    app = websocket.app
    config = getattr(app.state, "config", None)
    registry = getattr(app.state, "tool_registry", None)
    model_pool = getattr(app.state, "model_pool", None)
    chat_storage = getattr(app.state, "chat_storage", None)
    max_pairs = config.chat.max_history_pairs if config else 20
    save_threshold = config.chat.auto_save_after if config else 2

    # Per-connection model selection — use user preference if valid, else default
    current_model_id = model_pool.default_id if model_pool else None
    pref_model = (user.preferences or {}).get("model_id")
    if pref_model and model_pool and _resolve_model(model_pool, pref_model, config):
        current_model_id = pref_model

    # Per-connection chat tracking (mutable dict so background tasks can update it)
    chat = {"id": None, "messages": [], "title_generated": False, "model": current_model_id}

    try:
        # Send config, tool metadata, models, user, and initial status to frontend
        current_client = (
            _resolve_model(model_pool, current_model_id, config)
            if model_pool and current_model_id else None
        )
        tool_count = len(registry.all()) if registry else 0
        init_status = await _quick_status(current_client, tool_count=tool_count)
        await manager.send_json(conn_id, {
            "type": "init",
            "config": {
                "search_columns": (
                    config.search.columns
                    if config
                    else ["name", "size_bp", "topology", "features"]
                ),
                "max_history_pairs": max_pairs,
            },
            "tools": registry.metadata() if registry else [],
            "status": init_status,
            "models": [
                {"id": m.id, "provider": m.provider, "model": m.model}
                for m in model_pool.entries()
            ] if model_pool else [],
            "currentModel": current_model_id,
            "user": {
                "id": user.id,
                "username": user.username,
                "slug": user.slug,
                "preferences": user.preferences or {},
            },
        })

        while True:
            data = await websocket.receive_json()

            # Handle cancel — abort any running processing task
            if data.get("type") == "cancel":
                task = manager.tasks.get(conn_id)
                if task and not task.done():
                    task.cancel()
                continue

            # Handle model switch — seamless, no chat message
            if data.get("type") == "set_model":
                model_id = data.get("modelId")
                client = _resolve_model(
                    model_pool, model_id, config,
                ) if model_pool and model_id else None
                if client:
                    current_model_id = model_id
                    chat["model"] = model_id
                    await manager.send_json(conn_id, {
                        "type": "model_changed",
                        "modelId": model_id,
                    })
                    # Persist as user preference
                    if db.async_session_factory:
                        try:
                            async with db.async_session_factory() as s:
                                await update_preferences(
                                    s, user.id, "model_id", model_id,
                                )
                        except Exception as e:
                            logger.warning("Model pref save failed: %s", e)
                    logger.info("Connection %s switched to model %s", conn_id, model_id)
                continue

            # Handle preference update
            if data.get("type") == "set_preference" and db.async_session_factory:
                key = data.get("key")
                value = data.get("value")
                if key:
                    try:
                        async with db.async_session_factory() as s:
                            prefs = await update_preferences(s, user.id, key, value)
                        await manager.send_json(conn_id, {
                            "type": "preferences_updated",
                            "preferences": prefs,
                        })
                    except Exception as e:
                        logger.warning("Preference update failed: %s", e)
                continue

            # Handle feedback submission
            if data.get("type") == "submit_feedback" and db.async_session_factory:
                rating = data.get("rating", "")
                if rating in ("good", "bad"):
                    try:
                        async with db.async_session_factory() as s:
                            await create_feedback(
                                s,
                                user_id=user.id,
                                rating=rating,
                                priority=int(data.get("priority", 3)),
                                comment=data.get("comment", ""),
                                chat_id=chat.get("id"),
                            )
                        await manager.send_json(conn_id, {"type": "feedback_saved"})
                    except Exception as e:
                        logger.warning("Feedback save failed: %s", e)
                continue

            # Handle chat resume
            if data.get("type") == "load_chat" and chat_storage:
                requested_id = data.get("chatId")
                if requested_id:
                    saved = chat_storage.load(requested_id, user_slug)
                    if saved:
                        chat["id"] = requested_id
                        chat["messages"] = saved.get("messages", [])
                        chat["title_generated"] = bool(saved.get("title"))
                        manager.histories[conn_id] = [
                            {"role": m["role"], "content": m["content"]}
                            for m in chat["messages"]
                        ]
                        # Restore model from saved chat (fallback to default)
                        saved_model = saved.get("model")
                        if saved_model and model_pool and model_pool.get(saved_model):
                            current_model_id = saved_model
                        elif model_pool:
                            current_model_id = model_pool.default_id
                        chat["model"] = current_model_id
                        await manager.send_json(conn_id, {
                            "type": "chat_loaded",
                            "chatId": chat["id"],
                            "messages": chat["messages"],
                            "title": saved.get("title"),
                            "model": current_model_id,
                        })
                continue

            # Handle tool re-run (for stale widgets in loaded chats)
            if data.get("type") == "rerun_tool" and registry:
                tool_name = data.get("tool")
                params = data.get("params", {})
                message_index = data.get("messageIndex")
                tool = registry.get(tool_name) if tool_name else None
                if tool:
                    try:
                        result = await tool.execute(params, mode="rerun")
                        await manager.send_json(conn_id, {
                            "type": "widget_data",
                            "messageIndex": message_index,
                            "data": result,
                        })
                        if message_index is not None and 0 <= message_index < len(chat["messages"]):
                            w = chat["messages"][message_index].get("widget")
                            if w:
                                w["data"] = result
                                w.pop("stale", None)
                    except Exception as e:
                        logger.error("Re-run %s failed: %s", tool_name, e, exc_info=True)
                        await manager.send_json(conn_id, {
                            "type": "widget_data",
                            "messageIndex": message_index,
                            "data": {"error": "Tool execution failed. Check server logs."},
                        })
                continue

            content = data.get("content", "").strip()
            if not content:
                continue

            if not registry:
                await manager.send_json(conn_id, {
                    "type": "message",
                    "content": "Server not ready -- tool registry not initialized.",
                })
                continue

            # Resolve per-connection LLM client
            current_client = (
                _resolve_model(model_pool, current_model_id, config)
                if model_pool and current_model_id else None
            )

            # Process message as a cancellable background task
            manager.tasks[conn_id] = asyncio.create_task(
                _handle_message(
                    conn_id=conn_id,
                    content=content,
                    registry=registry,
                    llm_client=current_client,
                    model_id=current_model_id,
                    chat=chat,
                    chat_storage=chat_storage,
                    user_slug=user_slug,
                    max_pairs=max_pairs,
                    save_threshold=save_threshold,
                    config=config,
                )
            )

    except WebSocketDisconnect:
        manager.disconnect(conn_id)


async def _handle_message(
    conn_id: str,
    content: str,
    registry,
    llm_client,
    model_id: str | None,
    chat: dict,
    chat_storage,
    user_slug: str | None,
    max_pairs: int,
    save_threshold: int,
    config,
):
    """Process a user message — runs as a cancellable background task."""
    try:
        async def _progress(data: dict):
            await manager.send_json(conn_id, {"type": "progress", **data})

        result = await route_input(
            user_input=content,
            registry=registry,
            llm_client=llm_client,
            history=manager.get_history(conn_id),
            max_turns=config.llm.agent_max_turns if config else 5,
            pipe_min_length=config.llm.pipe_min_length if config else 200,
            on_progress=_progress,
        )

        # Track user message (skip bare commands that just show a form)
        manager.append_history(conn_id, "user", content, max_pairs)
        if result.get("type") != "form":
            chat["messages"].append({"role": "user", "content": content, "ts": _now_iso()})

        # Track assistant response
        assistant_content = result.get("content", "")
        if assistant_content:
            manager.append_history(conn_id, "assistant", assistant_content, max_pairs)

        # Build response — include model metadata
        response: dict = {"type": "message", "content": assistant_content, "model": model_id}

        if result.get("type") == "tool_result" and result.get("data"):
            tool_name = result["tool"]
            response["widget"] = {
                "type": _widget_type(tool_name, registry),
                "tool": tool_name,
                "params": result.get("params", {}),
                "data": result["data"],
            }
            if result.get("chain"):
                response["widget"]["chain"] = result["chain"]
        elif result.get("type") == "form":
            response["widget"] = {
                "type": "form",
                "tool": result["tool"],
                "params": {},
                "data": result["data"],
            }

        # Save assistant message (skip forms — they're ephemeral UI)
        if result.get("type") != "form":
            assistant_msg: dict = {
                "role": "assistant",
                "content": assistant_content,
                "ts": _now_iso(),
                "model": model_id,
            }
            if response.get("widget"):
                assistant_msg["widget"] = response["widget"]
            chat["messages"].append(assistant_msg)

        await manager.send_json(conn_id, response)

        # Send status update after tool results (counts may have changed)
        if result.get("type") == "tool_result":
            updated_status = await _quick_status(
                llm_client, tool_count=len(registry.all()) if registry else 0,
            )
            await manager.send_json(conn_id, {"type": "status_update", "status": updated_status})

        # Auto-save chat after threshold
        if chat_storage and manager.count_user_messages(conn_id) >= save_threshold:
            if chat["id"] is None:
                chat["id"] = chat_storage.new_chat_id()
            threshold = config.chat.widget_data_threshold if config else 2048
            messages_to_save = [_strip_large_widget_data(m, threshold) for m in chat["messages"]]
            chat_storage.save(
                chat["id"], messages_to_save, user_slug=user_slug, model=chat.get("model"),
            )

            # Generate title once via LLM
            if not chat["title_generated"] and llm_client:
                chat["title_generated"] = True
                title = await _generate_chat_title(llm_client, chat["messages"][:4])
                if title:
                    chat_storage.update_title(chat["id"], title, user_slug=user_slug)
                    await manager.send_json(conn_id, {
                        "type": "chat_saved",
                        "chatId": chat["id"],
                        "title": title,
                    })

    except asyncio.CancelledError:
        await manager.send_json(conn_id, {"type": "message", "content": "Cancelled."})
    except Exception as e:
        logger.error("Message processing failed: %s", e, exc_info=True)
        await manager.send_json(conn_id, {
            "type": "message",
            "content": "Something went wrong. Check server logs for details.",
        })
    finally:
        manager.tasks.pop(conn_id, None)


def _resolve_model(model_pool, model_id: str, config=None):
    """Get a client for configured or auto-discovered Ollama models."""
    client = model_pool.get(model_id)
    if client:
        return client
    # Auto-discovered Ollama model: register on the fly
    if model_id.startswith("ollama/") and config and config.llm.auto_discover:
        from hive.config import ModelEntry

        ollama_base = next(
            (e.base_url for e in model_pool.entries() if e.provider == "ollama"),
            "http://localhost:11434/v1",
        )
        entry = ModelEntry(
            provider="ollama",
            model=model_id.removeprefix("ollama/"),
            base_url=ollama_base,
        )
        return model_pool.get_or_create(model_id, entry)
    return None


async def _generate_chat_title(llm_client, messages: list[dict]) -> str | None:
    """Ask LLM to generate a short chat title from the first few messages."""
    try:
        summary_input = "\n".join(f"{m['role']}: {m['content'][:200]}" for m in messages)
        title_prompt = (
            "Generate a 2-word title for this chat. "
            "Reply with ONLY the title, no quotes, no punctuation."
        )
        resp = await llm_client.chat([
            {"role": "system", "content": title_prompt},
            {"role": "user", "content": summary_input},
        ])
        title = resp["choices"][0]["message"].get("content", "").strip().strip('"\'')
        if not title:
            return None
        # Enforce max 2 words
        words = title.split()
        return " ".join(words[:2])
    except Exception as e:
        logger.warning("Failed to generate chat title: %s", e)
        return None


def _strip_large_widget_data(msg: dict, threshold: int) -> dict:
    """Return a copy with large widget data replaced by a stale marker."""
    widget = msg.get("widget")
    if not widget or not widget.get("data") or widget.get("type") == "form":
        return msg
    data_size = len(json.dumps(widget["data"], default=str))
    if data_size > threshold:
        stripped = {**msg}
        stripped["widget"] = {
            "type": widget["type"],
            "tool": widget["tool"],
            "params": widget.get("params", {}),
            "stale": True,
        }
        return stripped
    return msg


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _widget_type(tool_name: str, registry=None) -> str:
    """Get widget type from the tool's own declaration."""
    if registry:
        tool = registry.get(tool_name)
        if tool:
            return tool.widget
    return "text"


async def _quick_status(llm_client=None, tool_count: int = 0) -> dict:
    """Lightweight status for the status bar (no full tool execution)."""
    status = {
        "indexed_files": 0, "sequences": 0, "features": 0, "users": 0,
        "tools": tool_count,
        "db_connected": False, "llm_available": False, "last_updated": None,
    }
    if db.async_session_factory:
        try:
            async with db.async_session_factory() as s:
                status["indexed_files"] = (await s.execute(
                    select(func.count())
                    .select_from(IndexedFile)
                    .where(IndexedFile.status == "active")
                )).scalar()
                status["sequences"] = (await s.execute(
                    select(func.count()).select_from(Sequence)
                )).scalar()
                status["features"] = (await s.execute(
                    select(func.count()).select_from(Feature)
                )).scalar()
                status["users"] = (await s.execute(
                    select(func.count()).select_from(User)
                )).scalar()
                last = (await s.execute(
                    select(func.max(IndexedFile.indexed_at))
                )).scalar()
                status["last_updated"] = last.isoformat() if last else None
            status["db_connected"] = True
        except Exception as e:
            logger.warning("Quick status DB query failed: %s", e)
    if llm_client:
        with contextlib.suppress(Exception):
            status["llm_available"] = await llm_client.health()
    return status
