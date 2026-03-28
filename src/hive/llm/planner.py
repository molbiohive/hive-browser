"""Planner agent -- produces a task plan for the worker."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from hive.llm.base import LLMAgent

if TYPE_CHECKING:
    from hive.llm.client import LLMClient
    from hive.tools import ToolRegistry

logger = logging.getLogger(__name__)

_SYSTEM = """\
You are a planning assistant for a lab sequence browser.

Available tools:
{catalog}

Write a SELF-CONTAINED task description for the worker LLM. \
The worker will NOT see the conversation history -- your plan must include \
all context it needs.

Rules:
- Include relevant context from history: IDs, names, constraints, prior results.
- For follow-ups ("that plasmid", "those results"): resolve references to concrete \
IDs/names/values from the conversation.
- For data questions: specify which operations and what to look for.
- For greetings/chat/general questions: just write "respond conversationally".
- Keep it concise (2-4 sentences). Only include context the worker actually needs.
- NEVER fabricate data, IDs, or results."""


class Planner(LLMAgent):
    """Plan generation agent.

    Single-turn loop that reads the tool catalog and conversation
    history to produce a self-contained task description for the worker.
    """

    def __init__(self, registry: ToolRegistry):
        super().__init__()
        sigs = registry.signatures(detailed=True)
        self._catalog = "\n".join(f"- {s}" for s in sigs)
        self._user_input = ""
        self._history: list[dict] | None = None

    def prepare(
        self,
        user_input: str,
        history: list[dict] | None = None,
    ) -> Planner:
        """Set context for the next run."""
        self._user_input = user_input
        self._history = history
        return self

    def _build_messages(self) -> list[dict]:
        system = _SYSTEM.format(catalog=self._catalog)
        messages: list[dict] = [{"role": "system", "content": system}]
        if self._history:
            messages.extend(self._history)
        messages.append({"role": "user", "content": self._user_input})
        return messages

    def _on_complete(self, content: str) -> tuple[str, dict[str, int]]:
        return content, dict(self.tokens)

    async def _on_exhausted(self) -> tuple[str, dict[str, int]]:
        return "", dict(self.tokens)
