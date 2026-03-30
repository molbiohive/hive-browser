"""Per-chat task list management."""

from __future__ import annotations

from uuid import uuid4

from hive.context import current_chat_tasks


def list_tasks() -> list[dict]:
    """Return the current chat's task list."""
    tasks = current_chat_tasks.get()
    return list(tasks) if tasks is not None else []


def add_task(text: str) -> dict:
    """Add a task to the current chat's list. Returns the new task."""
    tasks = current_chat_tasks.get()
    if tasks is None:
        raise RuntimeError("Task list not available (no active chat)")
    task = {"id": uuid4().hex[:8], "text": text, "done": False}
    tasks.append(task)
    return task


def toggle_task(task_id: str) -> bool:
    """Toggle a task's done state. Returns True if found."""
    tasks = current_chat_tasks.get()
    if tasks is None:
        raise RuntimeError("Task list not available (no active chat)")
    for t in tasks:
        if t["id"] == task_id:
            t["done"] = not t["done"]
            return True
    return False


def remove_task(task_id: str) -> bool:
    """Remove a task by ID. Returns True if found."""
    tasks = current_chat_tasks.get()
    if tasks is None:
        raise RuntimeError("Task list not available (no active chat)")
    before = len(tasks)
    tasks[:] = [t for t in tasks if t["id"] != task_id]
    return len(tasks) < before
