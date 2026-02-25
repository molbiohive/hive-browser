"""Tool interface and registry."""

from __future__ import annotations

import inspect
import json
import logging
from abc import ABC, abstractmethod
from functools import wraps
from typing import Any

logger = logging.getLogger(__name__)

# Known system tags — everything else is a group identifier
SYSTEM_TAGS = {"llm", "hidden"}


class Tool(ABC):
    """Base class for all tools (internal and external).

    Subclass attributes:
        name:        Tool identifier (used as registry key + LLM function name).
        description: Shown in help, command palette, and LLM prompts.
        widget:      Widget type for frontend rendering (maps to FooWidget.svelte).
        tags:        Behavioral flags + group identifiers. Known: "llm", "hidden".
        guidelines:  Concise LLM-facing description (used in tool schema if set).
        params:      Declarative param definitions for external tools (dict → JSON Schema).
    """

    name: str
    description: str
    widget: str = "text"
    tags: set[str] = {"llm"}
    guidelines: str = ""
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
                return {"error": f"Tool '{self.name}' failed. Check server logs."}

        cls.execute = _safe_execute

    @abstractmethod
    async def execute(self, params: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Execute the tool with the given parameters and return results.

        Standard kwargs passed by the router:
            mode: "direct" (//cmd), "guided" (/cmd), "natural" (LLM), "rerun" (widget refresh)

        Subclasses declare only the kwargs they need, e.g.:
            async def execute(self, params, mode="direct"):       # simple tool
            async def execute(self, params, mode="direct", user=None):  # user-aware
        """
        ...

    def input_schema(self) -> dict:
        """Return JSON Schema dict for this tool's parameters.

        Auto-generated from self.params if set.
        Internal tools override to use Pydantic model_json_schema().
        """
        if self.params:
            return _params_to_schema(self.params)
        return {"type": "object", "properties": {}}

    def format_result(self, result: dict) -> str:
        """Short summary for direct execution (no LLM). Override in subclasses."""
        if error := result.get("error"):
            return f"Error: {error}"
        return ""

    def summary_for_llm(self, result: dict, token_limit: int = 1000) -> str:
        """Compact result summary for LLM context. Do NOT override in subclasses."""
        max_chars = token_limit * 4
        max_items = max(5, token_limit // 50)
        return _auto_summarize(result, max_chars=max_chars, max_items=max_items)

    def schema(self) -> dict:
        """Full tool schema for LLM function calling."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.input_schema(),
        }

    def metadata(self) -> dict:
        """Metadata sent to the frontend on connect."""
        return {
            "name": self.name,
            "description": self.description,
            "widget": self.widget,
            "tags": sorted(self.tags),
        }

    def group(self) -> str | None:
        """Primary group tag (first non-system tag), or None."""
        for tag in self.tags:
            if tag not in SYSTEM_TAGS:
                return tag
        return None


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

    def llm_tools(self) -> list[Tool]:
        """Tools available to the LLM (tagged 'llm')."""
        return [t for t in self._tools.values() if "llm" in t.tags]

    def visible_tools(self) -> list[Tool]:
        """Tools visible in command palette (not tagged 'hidden')."""
        return [t for t in self._tools.values() if "hidden" not in t.tags]

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


def _auto_summarize(result: dict, max_chars: int = 4000, max_items: int = 20) -> str:
    """Generate compact descriptive stats from a result dict.

    - Lists → count + first max_items items as sample (default 20)
    - Numbers/booleans → include directly
    - Short strings (< 200 chars) → include
    - Long strings → truncate to 100 chars
    - Nested dicts → keep shallow scalar fields
    """
    stats: dict[str, Any] = {}

    for key, value in result.items():
        if isinstance(value, list):
            stats[f"{key}_count"] = len(value)
            if value and isinstance(value[0], dict):
                sample = []
                for item in value[:max_items]:
                    trimmed = {
                        k: v for k, v in item.items()
                        if isinstance(v, (str, int, float, bool, type(None)))
                        and (not isinstance(v, str) or len(v) < 200)
                    }
                    sample.append(trimmed)
                if sample:
                    stats[f"{key}_sample"] = sample
            elif value:
                stats[f"{key}_sample"] = value[:max_items]
        elif isinstance(value, (int, float, bool)):
            stats[key] = value
        elif isinstance(value, str):
            if len(value) < 200:
                stats[key] = value
            else:
                stats[key] = value[:100] + "..."
        elif isinstance(value, dict):
            # Keep shallow scalar fields from nested dicts
            shallow = {
                k: v for k, v in value.items()
                if isinstance(v, (str, int, float, bool, type(None)))
                and (not isinstance(v, str) or len(v) < 200)
            }
            if shallow:
                stats[key] = shallow

    text = json.dumps(stats, default=str)
    if len(text) > max_chars:
        text = text[:max_chars] + "..."
    return text
