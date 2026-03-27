"""Tasks tool -- manage per-chat task list."""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from hive.context import current_chat_tasks
from hive.tools.base import Tool

logger = logging.getLogger(__name__)


class TasksInput(BaseModel):
    action: str = Field(
        default="list",
        description="Action: add, toggle, remove, or list",
    )
    text: str | None = Field(default=None, description="Task text (for add)")
    task_id: str | None = Field(default=None, description="Task ID (for toggle/remove)")


class TasksTool(Tool):
    name = "tasks"
    description = ("task list", "Manage the chat task list.")
    tags = set()

    def __init__(self, **_):
        pass

    def input_schema(self) -> dict:
        schema = TasksInput.model_json_schema()
        schema.pop("title", None)
        return schema

    def format_result(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        tasks = result.get("tasks", [])
        done = sum(1 for t in tasks if t.get("done"))
        return f"{len(tasks)} task(s), {done} done"

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        inp = TasksInput(**params)
        tasks = current_chat_tasks.get()

        if tasks is None:
            return {"error": "Task list not available (no active chat)"}

        if inp.action == "add":
            if not inp.text:
                return {"error": "Provide text for the task"}
            task = {"id": uuid4().hex[:8], "text": inp.text, "done": False}
            tasks.append(task)
            return {"tasks": list(tasks)}

        if inp.action == "toggle":
            if not inp.task_id:
                return {"error": "Provide task_id to toggle"}
            for t in tasks:
                if t["id"] == inp.task_id:
                    t["done"] = not t["done"]
                    return {"tasks": list(tasks)}
            return {"error": f"Task not found: {inp.task_id}"}

        if inp.action == "remove":
            if not inp.task_id:
                return {"error": "Provide task_id to remove"}
            before = len(tasks)
            tasks[:] = [t for t in tasks if t["id"] != inp.task_id]
            if len(tasks) == before:
                return {"error": f"Task not found: {inp.task_id}"}
            return {"tasks": list(tasks)}

        # Default: list
        return {"tasks": list(tasks)}
