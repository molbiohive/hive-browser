"""Tool base class -- self-describing interface for all tools."""

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
        params:      Declarative param definitions for external tools (dict -> JSON Schema).
        advanced:    Param names hidden from sandbox/LLM signatures (still in full schema).
    """

    name: str
    description: tuple[str, str]
    tags: set[str] = set()
    params: dict | None = None
    advanced: set[str] = set()

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

    def api_schema(self) -> dict:
        """OpenAI-format schema for REST API docs."""
        return {
            "name": self.name,
            "description": self.long_desc,
            "parameters": self.input_schema(),
        }

    @property
    def short_desc(self) -> str:
        """Short label (1-3 words). Falls back to full description for plain strings."""
        return self.description[0] if isinstance(self.description, tuple) else self.description

    @property
    def long_desc(self) -> str:
        """Full description text. Falls back to full description for plain strings."""
        return self.description[1] if isinstance(self.description, tuple) else self.description

    def metadata(self) -> dict:
        """Metadata sent to the frontend on connect."""
        return {
            "name": self.name,
            "description": self.long_desc,
            "tags": sorted(self.tags),
            "schema": self.input_schema(),
            "advanced": sorted(self.advanced),
        }

    def group(self) -> str | None:
        """Primary group tag, or None."""
        if self.tags:
            return sorted(self.tags)[0]
        return None


_JSON_TO_PY = {"string": "str", "integer": "int", "number": "float", "boolean": "bool", "array": "list", "object": "dict"}


def _build_signature(tool: Tool) -> tuple[str, list[str]]:
    """Build ``name(param: type, ...)`` and param descriptions from input_schema().

    Params in ``tool.advanced`` are excluded from the signature.
    """
    schema = tool.input_schema()
    props = {k: v for k, v in schema.get("properties", {}).items() if k not in tool.advanced}
    required = set(schema.get("required", [])) - tool.advanced

    parts = []
    descs = []
    for name, spec in props.items():
        ptype = _JSON_TO_PY.get(spec.get("type", "string"), spec.get("type", "str"))
        if name in required:
            parts.append(f"{name}: {ptype}")
        else:
            parts.append(f"{name}: {ptype} | None = None")
        desc = spec.get("description")
        if desc:
            descs.append(f"{name}: {desc}")

    return f"{tool.name}({', '.join(parts)})", descs


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
