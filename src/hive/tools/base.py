"""Tool interface and registry."""

from __future__ import annotations

import inspect
import logging
from abc import ABC, abstractmethod
from functools import wraps
from typing import Any

logger = logging.getLogger(__name__)


class Tool(ABC):
    """Base class for all tools (internal and external).

    Subclass attributes:
        name:        Tool identifier (used as registry key + LLM function name).
        description: Tuple of (short_label, long_description).
                     short_label: 1-3 words for Available commands section.
                     long_description: full text for help, palette, forms.
        tags:        Group identifiers for UI categorization (e.g. "search", "analysis", "info").
        params:      Declarative param definitions for external tools (dict → JSON Schema).
    """

    name: str
    description: tuple[str, str]
    tags: set[str] = set()
    params: dict | None = None

    # Injected by factory for external tools
    db: Any = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if "execute" not in cls.__dict__:
            return
        original = cls.__dict__["execute"]
        # Pre-compute accepted params at class definition time
        sig = inspect.signature(original)
        accepted = set(sig.parameters.keys()) - {"self", "params"}

        @wraps(original)
        async def _safe_execute(self, params, **kw):
            try:
                filtered = {k: v for k, v in kw.items() if k in accepted}
                return await original(self, params, **filtered)
            except Exception as e:
                logger.error("Tool %s failed: %s", self.name, e, exc_info=True)
                return {"error": f"{type(e).__name__}: {str(e)[:200]}"}

        cls.execute = _safe_execute

    @abstractmethod
    async def execute(self, params: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Execute the tool with the given parameters and return results."""
        ...

    def input_schema(self) -> dict:
        """Return JSON Schema dict for this tool's parameters.

        Auto-generated from self.params if set.
        Internal tools override to use Pydantic model_json_schema().
        """
        if self.params:
            return _params_to_schema(self.params)
        return {"type": "object", "properties": {}}

    def llm_schema(self) -> dict:
        """Minimal schema for LLM function calling.

        Override to strip expert-only params. Default: input_schema().
        Skills system will provide custom params when needed.
        """
        return self.input_schema()

    def format_result(self, result: dict) -> str:
        """Short summary for direct execution (no LLM). Override in subclasses."""
        if error := result.get("error"):
            return f"Error: {error}"
        return ""

    @property
    def short_desc(self) -> str:
        """Short label (1-3 words). Falls back to full description for plain strings."""
        return self.description[0] if isinstance(self.description, tuple) else self.description

    @property
    def long_desc(self) -> str:
        """Full description text. Falls back to full description for plain strings."""
        return self.description[1] if isinstance(self.description, tuple) else self.description

    def schema(self) -> dict:
        """Full tool schema for LLM function calling."""
        return {
            "name": self.name,
            "description": self.long_desc,
            "parameters": self.input_schema(),
        }

    def metadata(self) -> dict:
        """Metadata sent to the frontend on connect."""
        return {
            "name": self.name,
            "description": self.long_desc,
            "tags": sorted(self.tags),
        }

    def group(self) -> str | None:
        """Primary group tag, or None."""
        if self.tags:
            return sorted(self.tags)[0]
        return None


class ToolRegistry:
    """Central registry of available tools."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool):
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def tools(self) -> list[Tool]:
        """All registered tools."""
        return list(self._tools.values())

    def metadata(self) -> list[dict]:
        """All tool metadata for frontend init."""
        return [t.metadata() for t in self._tools.values()]


def _params_to_schema(params: dict) -> dict:
    """Convert declarative param dict to JSON Schema.

    Input format:
        {"query": {"type": "string", "description": "Search text", "required": True},
         "limit": {"type": "integer", "description": "Max results", "default": 10}}

    Supported keys per param: type, description, required, default, enum.
    """
    properties = {}
    required = []

    for name, spec in params.items():
        prop: dict[str, Any] = {}
        if "type" in spec:
            prop["type"] = spec["type"]
        if "description" in spec:
            prop["description"] = spec["description"]
        if "default" in spec:
            prop["default"] = spec["default"]
        if "enum" in spec:
            prop["enum"] = spec["enum"]
        properties[name] = prop

        if spec.get("required", False):
            required.append(name)

    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema
