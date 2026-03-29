"""ToolRegistry -- central registry of available tools."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hive.tools.base import Tool

from hive.tools.base import _build_signature


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

    def filtered(self, names: list[str]) -> ToolRegistry:
        """Return a new registry containing only the named tools."""
        new = ToolRegistry()
        for name in names:
            if tool := self._tools.get(name):
                new.register(tool)
        return new

    def metadata(self) -> list[dict]:
        """All tool metadata for frontend init."""
        return [t.metadata() for t in self._tools.values()]

    def signatures(self, detailed: bool = False) -> list[str]:
        """Python-style tool signatures for LLM context.

        When detailed=False (workspace):
            ``def search(query: str, tags: str | None = None) -> dict  # fuzzy search``
        When detailed=True (planner catalog): adds indented param descriptions.
        """
        lines = []
        for tool in self._tools.values():
            sig, descs = _build_signature(tool)
            lines.append(f"{sig} -> dict  # {tool.short_desc}")
            if detailed:
                for d in descs:
                    lines.append(f"  {d}")
        return lines
