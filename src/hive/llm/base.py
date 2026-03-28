"""Base LLM agent with agentic loop."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hive.llm.client import LLMClient

logger = logging.getLogger(__name__)


class LLMAgent:
    """Agentic loop base for planner and worker.

    The loop: build messages -> call LLM -> handle tool calls -> repeat.
    Messages are rebuilt each turn via ``_build_messages()`` (flat context).
    Subclasses carry their own context (user input, history, workspace)
    and override hooks to customize behavior.

    Hooks (override in subclasses):
        _build_messages  -- assemble the message list for this turn
        _tools           -- return tool schemas (None = no tools)
        _handle_call     -- process a single tool call
        _on_complete     -- format result from text response
        _on_exhausted    -- format result when max turns reached or error
        _on_error        -- handle LLM error; return True to retry turn
        _pre_run         -- async setup after reset, before first turn
        _post_turn       -- called after each turn's tool calls
    """

    def __init__(self):
        self.tokens: dict[str, int] = {"in": 0, "out": 0}
        self._llm: LLMClient | None = None

    def _reset(self):
        """Reset per-run state."""
        self.tokens = {"in": 0, "out": 0}

    # -- Agentic loop --

    async def run(self, llm: LLMClient, max_turns: int = 1) -> Any:
        """Run the agentic loop.

        Each turn: _build_messages -> _chat -> if tool_calls: _handle_call
        -> _post_turn -> next turn. Loop ends on text response, refusal,
        max turns, or unrecoverable error.
        """
        self._reset()
        self._llm = llm
        await self._pre_run()

        for turn in range(max_turns):
            messages = self._build_messages()
            tools = self._tools()

            try:
                response = await self._chat(llm, messages, tools)
            except Exception as e:
                if await self._on_error(e, turn):
                    continue
                break

            finish = response["choices"][0].get("finish_reason", "")
            if finish == "refusal":
                content = self._msg_content(response)
                return self._on_complete(content or "Request declined by the model.")

            calls = self._msg_tool_calls(response)
            if not calls:
                return self._on_complete(self._msg_content(response))

            for tc in calls:
                await self._handle_call(tc)

            await self._post_turn(turn)

        return await self._on_exhausted()

    # -- Hooks --

    def _build_messages(self) -> list[dict]:
        """Assemble message list for this turn. MUST override."""
        raise NotImplementedError

    def _tools(self) -> list[dict] | None:
        """Tool schemas for LLM. None = no tool calling."""
        return None

    async def _handle_call(self, tc: dict) -> None:
        """Process a tool call. Override to execute tools and record results."""

    def _on_complete(self, content: str) -> Any:
        """Handle final text response from LLM."""
        return content

    async def _on_exhausted(self) -> Any:
        """Handle loop end (max turns or error break)."""
        return ""

    async def _on_error(self, error: Exception, turn: int) -> bool:
        """Handle LLM call error. Return True to retry the turn."""
        logger.error("LLM call failed (turn %d): %s", turn, error)
        return False

    async def _pre_run(self) -> None:
        """Called after reset, before the first turn."""

    async def _post_turn(self, turn: int) -> None:
        """Called after processing all tool calls in a turn."""

    # -- LLM call --

    async def _chat(
        self,
        llm: LLMClient,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> dict:
        """Make an LLM call, accumulating token usage."""
        response = await llm.chat(messages, tools=tools)
        usage = response.get("usage") or {}
        self.tokens["in"] += usage.get("prompt_tokens", 0)
        self.tokens["out"] += usage.get("completion_tokens", 0)
        return response

    # -- Utilities --

    @staticmethod
    def _msg_content(response: dict) -> str:
        """Extract text content from an LLM response."""
        return (response["choices"][0]["message"].get("content") or "").strip()

    @staticmethod
    def _msg_tool_calls(response: dict) -> list[dict]:
        """Extract tool_calls (empty list if none)."""
        return response["choices"][0]["message"].get("tool_calls") or []

    @staticmethod
    def _parse_tool_args(tc: dict) -> dict[str, Any]:
        """Parse tool call arguments, stripping None values."""
        raw = tc["function"]["arguments"]
        try:
            params = json.loads(raw) if isinstance(raw, str) else raw
            return {k: v for k, v in params.items() if v is not None}
        except (json.JSONDecodeError, AttributeError):
            return {}

    @staticmethod
    def _sanitize_error(raw: str) -> str:
        """Turn raw LLM exceptions into short user-facing messages."""
        lowered = raw.lower()
        if "rate" in lowered and "limit" in lowered:
            return "Rate limit reached"
        if "auth" in lowered:
            return "LLM auth failed"
        if "timeout" in lowered:
            return "LLM request timed out"
        if "connect" in lowered:
            return "Could not connect to LLM"
        first = raw.split(".")[0].split("\n")[0]
        return first[:120] if len(first) > 120 else first
