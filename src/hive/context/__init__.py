"""Request-scoped context variables."""

from contextvars import ContextVar

current_user_id: ContextVar[int | None] = ContextVar("current_user_id", default=None)
current_chat_tasks: ContextVar[list | None] = ContextVar("current_chat_tasks", default=None)
