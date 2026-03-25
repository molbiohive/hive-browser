"""Planner — cheap LLM call to produce a task description for the agent."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from hive.llm.prompts import build_plan_messages, build_tool_catalog

if TYPE_CHECKING:
    from hive.llm.client import LLMClient
    from hive.tools.base import Tool

logger = logging.getLogger(__name__)


class Planner:
    """Produces a task description from user input via a cheap LLM call.

    The plan text is injected into the agent's user message so it has
    context about what operations to perform.
    """

    def __init__(self, tools: list[Tool]):
        self._catalog = build_tool_catalog(tools)

    async def plan(
        self,
        user_input: str,
        llm_client: LLMClient,
        history: list[dict] | None = None,
    ) -> tuple[str, dict[str, int]]:
        """Run the planning call. Returns (plan_text, usage_dict)."""
        messages = build_plan_messages(self._catalog, user_input, history)
        response = await llm_client.chat(messages)

        usage = response.get("usage") or {}
        usage_dict = {
            "in": usage.get("prompt_tokens", 0),
            "out": usage.get("completion_tokens", 0),
        }

        raw = (response["choices"][0]["message"].get("content") or "").strip()
        return raw, usage_dict
