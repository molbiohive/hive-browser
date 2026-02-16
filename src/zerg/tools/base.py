"""Tool interface and registry."""

from __future__ import annotations

import importlib
import logging
import pkgutil
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from zerg.config import Settings
    from zerg.llm.client import LLMClient

logger = logging.getLogger(__name__)


class ToolInput(BaseModel):
    """Base input schema — tools extend this."""
    pass


class ToolOutput(BaseModel):
    """Base output schema — tools extend this."""
    pass


class Tool(ABC):
    """Base class for all tools. Each tool has a name, description, and execute method."""

    name: str
    description: str
    widget_type: str = "text"
    use_llm: bool = True

    @abstractmethod
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """Execute the tool with the given parameters and return results."""
        ...

    def schema(self) -> dict:
        """Return the tool's parameter schema for LLM function calling."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.input_schema().model_json_schema(),
        }

    @abstractmethod
    def input_schema(self) -> type[ToolInput]:
        """Return the Pydantic model class for this tool's input."""
        ...

    def format_result(self, result: dict) -> str:
        """Format tool result as a short summary. Override in subclasses."""
        if error := result.get("error"):
            return f"Error: {error}"
        return ""

    def metadata(self) -> dict:
        """Metadata sent to the frontend on connect."""
        return {
            "name": self.name,
            "description": self.description,
            "widget_type": self.widget_type,
            "use_llm": self.use_llm,
        }


class ToolRegistry:
    """Central registry of available tools."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool):
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def schemas(self) -> list[dict]:
        """All tool schemas for LLM function calling."""
        return [t.schema() for t in self._tools.values()]

    def metadata(self) -> list[dict]:
        """All tool metadata for frontend init."""
        return [t.metadata() for t in self._tools.values()]

    @classmethod
    def auto_discover(cls, config: Settings | None = None, llm_client: LLMClient | None = None) -> ToolRegistry:
        """Scan zerg.tools.* modules for create() factories and build a registry."""
        import zerg.tools as tools_pkg

        registry = cls()
        for info in pkgutil.iter_modules(tools_pkg.__path__):
            if info.name in ("base", "router"):
                continue
            try:
                mod = importlib.import_module(f"zerg.tools.{info.name}")
                factory = getattr(mod, "create", None)
                if factory:
                    tool = factory(config=config, llm_client=llm_client)
                    registry.register(tool)
                    logger.debug("Auto-registered tool: %s", tool.name)
            except Exception as e:
                logger.warning("Failed to load tool %s: %s", info.name, e)
        return registry
