"""Tool interface and registry."""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


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
