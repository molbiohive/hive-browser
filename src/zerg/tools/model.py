"""Model tool — show LLM configuration and connection status."""

from typing import Any

from zerg.config import LLMConfig
from zerg.llm.client import LLMClient
from zerg.tools.base import Tool, ToolInput


class ModelInput(ToolInput):
    pass


class ModelTool(Tool):
    name = "model"
    description = "Show LLM model name, endpoint URL, and connection status."
    widget_type = "model"

    def __init__(self, config: LLMConfig, llm_client: LLMClient | None = None):
        self._config = config
        self._llm = llm_client

    def input_schema(self) -> type[ToolInput]:
        return ModelInput

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        connected = False
        if self._llm:
            try:
                connected = await self._llm.health()
            except Exception:
                pass

        return {
            "model": self._config.model,
            "base_url": self._config.base_url,
            "connected": connected,
        }

    def format_result(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        status = "connected" if result.get("connected") else "disconnected"
        return f"Model: {result.get('model', 'unknown')} ({status})"
