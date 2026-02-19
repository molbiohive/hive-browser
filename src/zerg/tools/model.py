"""Model tool — show LLM configuration and connection status."""

from __future__ import annotations

import contextlib
from typing import Any

from zerg.tools.base import Tool


class ModelTool(Tool):
    name = "model"
    description = "Show LLM model name, endpoint URL, and connection status."
    widget = "model"
    tags = {"info"}

    def __init__(self, config=None, llm_client=None, **_):
        if not config:
            raise ValueError("ModelTool requires config")
        self._config = config.llm
        self._llm = llm_client

    def input_schema(self) -> dict:
        return {"type": "object", "properties": {}}

    def format_result(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        status = "connected" if result.get("connected") else "disconnected"
        provider = result.get("provider", "unknown")
        return f"Model: {result.get('model', 'unknown')} via {provider} ({status})"

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        connected = False
        if self._llm:
            with contextlib.suppress(Exception):
                connected = await self._llm.health()

        return {
            "provider": self._config.provider,
            "model": self._config.model,
            "base_url": self._config.base_url,
            "connected": connected,
        }
