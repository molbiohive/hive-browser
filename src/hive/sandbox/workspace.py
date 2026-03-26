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

    Two namespaces:
      - ``p0, p1, ...`` — pipeline handles (ephemeral, erased between messages)
      - ``r0, r1, ...`` — report handles (persist across messages, capped)

    Stores any value type: str, list[dict], dict, list[int], etc.
    """

    def __init__(self):
        self._entries: list[WorkspaceEntry] = []

    def store(
        self, key: str, value: Any, tool: str, params: dict[str, Any] | None = None,
        prefix: str = "p",
    ) -> str:
        """Store *value* under field name *key*, return handle.

        prefix='p' for pipeline (ephemeral), 'r' for report (persists).
        """
        count = sum(1 for e in self._entries if e.handle.startswith(prefix))
        handle = f"{prefix}{count}"
        self._entries.append(WorkspaceEntry(handle, value, key, tool, params or {}))
        return handle

    def get(self, handle: str) -> Any | None:
        """Retrieve value by handle, or None."""
        entry = self._find_entry(handle)
        if entry is None:
            return None
        return entry.value

    def describe(self, handle: str) -> str:
        """One-line description of a handle."""
        entry = self._find_entry(handle)
        if entry is None:
            return ""
        detail = _detail(entry.value)
        return f"{entry.handle}: {entry.field_name} ({entry.type_desc}{detail}) from {entry.tool}"

    def describe_compact(self, handle: str) -> str:
        """Ultra-compact: 'r0: field (type) from tool' — no column names or details."""
        entry = self._find_entry(handle)
        if entry is None:
            return ""
        return f"{entry.handle}: {entry.field_name} ({entry.type_desc}) from {entry.tool}"

    def describe_all(self, max_entries: int = 50) -> str:
        """All handles, one per line. Skips _result meta-handles. Capped."""
        visible = [
            e for e in self._entries
            if e.field_name != "_result"
        ]
        lines = [self.describe(e.handle) for e in visible[:max_entries] if self.describe(e.handle)]
        if len(visible) > max_entries:
            lines.append(f"... and {len(visible) - max_entries} more handles")
        return "\n".join(lines)

    def describe_handles(self, handles: list[str]) -> str:
        """Describe only the given handles, one per line. Skips _result."""
        return "\n".join(
            self.describe(h)
            for h in handles
            if self._find_entry(h) and self._find_entry(h).field_name != "_result" and self.describe(h)
        )

    def namespace(self) -> dict[str, Any]:
        """Handles as Python variables for sandbox injection."""
        return {entry.handle: entry.value for entry in self._entries}

    def store_result(
        self,
        result: dict[str, Any],
        tool: str,
        params: dict[str, Any] | None = None,
    ) -> list[str]:
        """Store full tool result and break out complex sub-values.

        Always stores the complete result dict as ``_result``.  Then stores
        lists, large strings (>=200 chars), and dicts (>2 keys) as separate
        entries for direct sandbox access.  Python references are shared --
        no memory duplication.

        Returns list of new handle names created by this call.
        """
        p = params or {}
        handles: list[str] = []
        handles.append(self.store("_result", result, tool, p))
        for key, val in result.items():
            if key == "error":
                continue
            if (
                isinstance(val, list)
                and val
                or isinstance(val, str)
                and len(val) >= 200
                or isinstance(val, dict)
                and len(val) > 2
            ):
                handles.append(self.store(key, val, tool, p))
        return handles

    def find_by_field(self, field_name: str, min_length: int = 0) -> str | None:
        """Find most recent string whose field name matches.

        Only returns string values at least *min_length* chars long.
        Used for auto-fill (piping sequences between tools).
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
        return self._find_entry(handle) is not None

    # ── Trimming ──

    def trim_between_messages(self, max_report: int = 10) -> None:
        """Erase all p<N> handles. Keep last *max_report* r<N> handles, re-index."""
        report_entries = [e for e in self._entries if e.handle.startswith("r")]
        kept = report_entries[-max_report:]
        for i, entry in enumerate(kept):
            entry.handle = f"r{i}"
        self._entries = kept

    # ── Serialization ──

    def to_json(self) -> list[dict]:
        """Serialize entries for persistence."""
        out = []
        for e in self._entries:
            out.append(
                {
                    "handle": e.handle,
                    "field_name": e.field_name,
                    "tool": e.tool,
                    "params": e.params,
                    "type_desc": e.type_desc,
                    "value": e.value,
                }
            )
        return out

    @classmethod
    def from_json(cls, data: list[dict]) -> Workspace:
        """Reconstruct workspace from saved JSON."""
        ws = cls()
        for item in data:
            entry = WorkspaceEntry(
                handle=item["handle"],
                value=item.get("value"),
                field_name=item["field_name"],
                tool=item["tool"],
                params=item.get("params", {}),
            )
            entry.type_desc = item.get("type_desc", _type_desc(entry.value))
            ws._entries.append(entry)
        return ws

    def _find_entry(self, handle: str) -> WorkspaceEntry | None:
        """Find entry by handle name (supports both p<N> and r<N>)."""
        for entry in self._entries:
            if entry.handle == handle:
                return entry
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
            sample = _sample_row(value[0])
            return f", {len(value)} rows — sample: {sample}"
        return f", {len(value)} items"
    if isinstance(value, dict):
        return _dict_detail(value)
    return ""


def _sample_row(row: dict, max_keys: int = 8) -> str:
    """Show first row with value types and previews."""
    parts: list[str] = []
    for key, val in list(row.items())[:max_keys]:
        parts.append(f"{key}: {_val_preview(val)}")
    if len(row) > max_keys:
        parts.append("...")
    return "{" + ", ".join(parts) + "}"


def _val_preview(val: Any) -> str:
    """Short preview of a value showing type + content."""
    if val is None:
        return "None"
    if isinstance(val, bool):
        return str(val)
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, str):
        if len(val) <= 40:
            return repr(val)
        return f"str({len(val)})"
    if isinstance(val, list):
        if not val:
            return "[]"
        if isinstance(val[0], str):
            preview = ", ".join(repr(v) for v in val[:3])
            suffix = ", ..." if len(val) > 3 else ""
            return f"[{preview}{suffix}]"
        return f"list({len(val)})"
    if isinstance(val, dict):
        return f"dict({len(val)})"
    return type(val).__name__


def _dict_detail(d: dict) -> str:
    """Inline scalars + type hints for complex values, capped at 8 entries."""
    parts: list[str] = []
    for key, val in list(d.items())[:8]:
        if isinstance(val, (int, float, bool)):
            parts.append(f"{key}={val}")
        elif isinstance(val, str):
            if len(val) <= 80:
                parts.append(f"{key}={val}")
            else:
                parts.append(f"{key}=str({len(val)})")
        elif isinstance(val, list):
            parts.append(f"{key}=list({len(val)})")
        elif isinstance(val, dict):
            parts.append(f"{key}=dict({len(val)})")
        elif val is None:
            parts.append(f"{key}=None")
    if len(d) > 8:
        parts.append("...")
    return f" -- {', '.join(parts)}" if parts else ""
