"""Model tool — show LLM configuration and connection status."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from zerg.config import LLMConfig
from zerg.llm.client import LLMClient
from zerg.tools.base import Tool, ToolInput

if TYPE_CHECKING:
    from zerg.config import Settings


def create(config: Settings | None = None, llm_client: LLMClient | None = None) -> Tool:
    if not config:
        raise ValueError("ModelTool requires config")
    return ModelTool(config=config.llm, llm_client=llm_client)


class ModelInput(ToolInput):
    pass


class ModelTool(Tool):
    name = "model"
    description = "Show LLM model name, endpoint URL, and connection status."
    widget_type = "model"
    use_llm = False

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
            "provider": self._config.provider,
            "model": self._config.model,
            "base_url": self._config.base_url,
            "connected": connected,
        }

    def format_result(self, result: dict) -> str:
        if error := result.get("error"):
            return f"Error: {error}"
        status = "connected" if result.get("connected") else "disconnected"
        provider = result.get("provider", "unknown")
        return f"Model: {result.get('model', 'unknown')} via {provider} ({status})"
