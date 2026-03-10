"""Workspace -- per-loop data store for all tool results."""

from __future__ import annotations

from typing import Any


class WorkspaceEntry:
    """Single stored value with metadata."""

    __slots__ = ("handle", "value", "field_name", "tool", "params", "type_desc")

    def __init__(
        self,
        handle: str,
        value: Any,
        field_name: str,
        tool: str,
        params: dict[str, Any],
    ):
        self.handle = handle
        self.value = value
        self.field_name = field_name
        self.tool = tool
        self.params = params
        self.type_desc = _type_desc(value)


class Workspace:
    """Per-loop data store. All tool results cached as named handles.

    Handles are named r0, r1, r2, ... (sequential, LLM-friendly).
    Stores any value type: str, list[dict], dict, list[int], etc.
    """

    def __init__(self):
        self._entries: list[WorkspaceEntry] = []

    def store(self, key: str, value: Any, tool: str, params: dict[str, Any] | None = None) -> str:
        """Store *value* under field name *key*, return handle (r0, r1, ...)."""
        handle = f"r{len(self._entries)}"
        self._entries.append(WorkspaceEntry(handle, value, key, tool, params or {}))
        return handle

    def get(self, handle: str) -> Any | None:
        """Retrieve value by handle, or None."""
        idx = self._handle_index(handle)
        if idx is None:
            return None
        return self._entries[idx].value

    def describe(self, handle: str) -> str:
        """One-line description of a handle.

        Examples:
            r0: 41 rows (list[dict]) from search [sid, name, ...]
            r1: sequence (str, 4521 chars) from profile
            r2: fragments (list[int], 3 items) from digest
        """
        idx = self._handle_index(handle)
        if idx is None:
            return ""
        entry = self._entries[idx]
        detail = _detail(entry.value)
        return f"{handle}: {entry.field_name} ({entry.type_desc}{detail}) from {entry.tool}"

    def describe_all(self) -> str:
        """All handles, one per line."""
        lines = []
        for i in range(len(self._entries)):
            lines.append(self.describe(f"r{i}"))
        return "\n".join(lines)

    def namespace(self) -> dict[str, Any]:
        """All handles as Python variables for sandbox injection."""
        return {entry.handle: entry.value for entry in self._entries}

    def find_by_field(self, field_name: str, min_length: int = 0) -> str | None:
        """Find most recent stored string whose field name matches.

        Only returns string values at least *min_length* chars long.
        Used for auto-fill (piping sequences between tools).
        Non-string data (lists, dicts) should be accessed via sandbox handles.
        """
        for entry in reversed(self._entries):
            if entry.field_name != field_name:
                continue
            if not isinstance(entry.value, str):
                continue
            if len(entry.value) < min_length:
                continue
            return entry.value
        return None

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, handle: str) -> bool:
        idx = self._handle_index(handle)
        return idx is not None and idx < len(self._entries)

    def _handle_index(self, handle: str) -> int | None:
        if not handle.startswith("r"):
            return None
        try:
            idx = int(handle[1:])
        except ValueError:
            return None
        if 0 <= idx < len(self._entries):
            return idx
        return None


def _type_desc(value: Any) -> str:
    """Short type description for a value."""
    if isinstance(value, list):
        if value and isinstance(value[0], dict):
            return "list[dict]"
        if value and isinstance(value[0], int):
            return "list[int]"
        return "list"
    if isinstance(value, dict):
        return "dict"
    if isinstance(value, str):
        return "str"
    return type(value).__name__


def _detail(value: Any) -> str:
    """Size detail string for describe()."""
    if isinstance(value, str):
        return f", {len(value)} chars"
    if isinstance(value, list):
        if value and isinstance(value[0], dict):
            cols = _column_names(value)
            return f", {len(value)} rows [{', '.join(cols)}]"
        return f", {len(value)} items"
    if isinstance(value, dict):
        keys = list(value.keys())[:6]
        if len(value) > 6:
            keys.append("...")
        return f", {len(value)} keys [{', '.join(str(k) for k in keys)}]"
    return ""


def _column_names(rows: list[dict], max_cols: int = 8) -> list[str]:
    """Extract column names from the first row, capped at *max_cols*."""
    if not rows:
        return []
    keys = list(rows[0].keys())[:max_cols]
    if len(rows[0]) > max_cols:
        keys.append("...")
    return keys
