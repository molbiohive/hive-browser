"""ResultCache -- per-loop storage for list[dict] tool results."""

from __future__ import annotations

from typing import Any


class CacheEntry:
    """Single cached result set."""

    __slots__ = ("rows", "tool", "params")

    def __init__(self, rows: list[dict], tool: str, params: dict[str, Any]):
        self.rows = rows
        self.tool = tool
        self.params = params


class ResultCache:
    """Auto-incrementing cache for list[dict] tool results.

    Handles are named r0, r1, r2, etc.  Each entry stores the rows
    plus metadata about which tool produced them.
    """

    def __init__(self):
        self._entries: list[CacheEntry] = []

    def store(self, rows: list[dict], tool: str, params: dict[str, Any] | None = None) -> str:
        """Cache *rows* and return its handle (r0, r1, ...)."""
        handle = f"r{len(self._entries)}"
        self._entries.append(CacheEntry(rows, tool, params or {}))
        return handle

    def get(self, handle: str) -> list[dict] | None:
        """Return cached rows for *handle*, or None."""
        idx = self._handle_index(handle)
        if idx is None:
            return None
        return self._entries[idx].rows

    def describe(self, handle: str) -> str:
        """One-line description: 'r0: 41 rows from search [sid, name, ...]'."""
        idx = self._handle_index(handle)
        if idx is None:
            return ""
        entry = self._entries[idx]
        cols = _column_names(entry.rows)
        return f"{handle}: {len(entry.rows)} rows from {entry.tool} [{', '.join(cols)}]"

    def describe_all(self) -> str:
        """All handles, one per line."""
        lines = []
        for i in range(len(self._entries)):
            lines.append(self.describe(f"r{i}"))
        return "\n".join(lines)

    def namespace(self) -> dict[str, list[dict]]:
        """Dict mapping handle names to row lists, for exec injection."""
        return {f"r{i}": entry.rows for i, entry in enumerate(self._entries)}

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


def _column_names(rows: list[dict], max_cols: int = 8) -> list[str]:
    """Extract column names from the first row, capped at *max_cols*."""
    if not rows:
        return []
    keys = list(rows[0].keys())[:max_cols]
    if len(rows[0]) > max_cols:
        keys.append("...")
    return keys
