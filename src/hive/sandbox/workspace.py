"""Workspace -- per-loop data store and LLM context hub."""

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
        self.type_desc = _type_label(value)


class Workspace:
    """Central data context for the LLM agent.

    Holds three kinds of data:
      - **Handles** (p0, p1, r0, r1, ...) — tool results stored by the router.
      - **User variables** — Python variables persisted across sandbox calls.
      - **Step history** — compact log of what the LLM has done.

    Two methods produce all LLM-facing context:
      - ``describe()`` — current scope (what data exists and how to access it).
      - ``history()``  — progress (what was done and what happened).
    """

    def __init__(self):
        self._entries: list[WorkspaceEntry] = []
        self._user_vars: dict[str, Any] = {}
        self._steps: list[dict] = []

    # ── Core storage ──

    def store(
        self, key: str, value: Any, tool: str, params: dict[str, Any] | None = None,
        prefix: str = "p",
    ) -> str:
        """Store *value* under field name *key*, return handle."""
        count = sum(1 for e in self._entries if e.handle.startswith(prefix))
        handle = f"{prefix}{count}"
        self._entries.append(WorkspaceEntry(handle, value, key, tool, params or {}))
        return handle

    def get(self, handle: str) -> Any | None:
        entry = self._find_entry(handle)
        return entry.value if entry else None

    def store_result(
        self,
        result: dict[str, Any],
        tool: str,
        params: dict[str, Any] | None = None,
    ) -> list[str]:
        """Store full tool result, break out complex sub-values. Returns new handles."""
        p = params or {}
        handles: list[str] = []
        handles.append(self.store("_result", result, tool, p))
        for key, val in result.items():
            if key == "error":
                continue
            if (
                isinstance(val, list) and val
                or isinstance(val, str) and len(val) >= 200
                or isinstance(val, dict) and len(val) > 2
            ):
                handles.append(self.store(key, val, tool, p))
        return handles

    def find_by_field(self, field_name: str, min_length: int = 0) -> str | None:
        """Find most recent string value matching field name."""
        for entry in reversed(self._entries):
            if entry.field_name != field_name:
                continue
            if not isinstance(entry.value, str):
                continue
            if len(entry.value) < min_length:
                continue
            return entry.value
        return None

    def namespace(self) -> dict[str, Any]:
        """All handles as Python variables for sandbox injection."""
        return {entry.handle: entry.value for entry in self._entries}

    # ── User variables (persisted across sandbox calls within a message) ──

    @property
    def user_vars(self) -> dict[str, Any]:
        return self._user_vars

    def update_vars(self, new_vars: dict[str, Any]) -> None:
        self._user_vars.update(new_vars)

    # ── Step tracking (replaces turn_log) ──

    def add_step(
        self, tool: str, feedback: str,
        code: str | None = None, error: str | None = None,
    ) -> None:
        self._steps.append({
            "tool": tool, "feedback": feedback, "code": code, "error": error,
        })

    @property
    def steps(self) -> list[dict]:
        return self._steps

    # ── LLM context: describe() + history() ──

    def describe(self, report: dict[str, Any] | None = None) -> str:
        """Full current scope — everything the LLM can access right now.

        Groups: pipeline handles → user variables → report entries → persistent handles.
        Uses ``describe_value()`` for structure introspection.
        """
        lines: list[str] = []

        # Pipeline handles (current message)
        for e in self._entries:
            if e.field_name == "_result" or e.handle.startswith("r"):
                continue
            lines.append(
                f"  {e.handle}: {e.field_name} — {describe_value(e.value)} [from {e.tool}]"
            )

        # User variables from previous python calls
        for name in sorted(self._user_vars):
            lines.append(f"  {name} — {describe_value(self._user_vars[name])}")

        # Report entries (sandbox report dict)
        if report:
            for key, val in report.items():
                lines.append(f'  report["{key}"] — {describe_value(val)}')

        # Persistent handles from previous messages
        for e in self._entries:
            if e.handle.startswith("r") and e.field_name != "_result":
                lines.append(
                    f"  {e.handle}: {e.field_name} — {describe_value(e.value)} [from {e.tool}]"
                )

        return "\n".join(lines) if lines else "Empty."

    def history(self, max_steps: int = 5) -> str:
        """Compact progress log for LLM context.

        Shows numbered steps with tool, truncated code, and feedback/error.
        """
        if not self._steps:
            return ""
        recent = self._steps[-max_steps:]
        lines: list[str] = []
        offset = len(self._steps) - len(recent)
        if offset > 0:
            lines.append(f"({offset} earlier steps omitted)")
        for i, s in enumerate(recent):
            n = offset + i + 1
            if s["error"]:
                if s["code"]:
                    brief = _truncate(s["code"], 80)
                    lines.append(f"{n}. python: `{brief}` → Error: {s['error']}")
                else:
                    lines.append(f"{n}. {s['tool']}: Error: {s['error']}")
            elif s["code"]:
                brief = _truncate(s["code"], 80)
                lines.append(f"{n}. python: `{brief}` → {s['feedback']}")
            else:
                lines.append(f"{n}. {s['tool']}: {s['feedback']}")
        return "\n".join(lines)

    # ── Lifecycle ──

    def reset_loop(self) -> None:
        """Clear per-message state (user variables, step history)."""
        self._user_vars.clear()
        self._steps.clear()

    def trim_between_messages(self, max_report: int = 10) -> None:
        """Erase all p<N> handles. Keep last *max_report* r<N> handles, re-index."""
        report_entries = [e for e in self._entries if e.handle.startswith("r")]
        kept = report_entries[-max_report:]
        for i, entry in enumerate(kept):
            entry.handle = f"r{i}"
        self._entries = kept

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, handle: str) -> bool:
        return self._find_entry(handle) is not None

    # ── Serialization ──

    def to_json(self) -> list[dict]:
        out = []
        for e in self._entries:
            out.append({
                "handle": e.handle,
                "field_name": e.field_name,
                "tool": e.tool,
                "params": e.params,
                "type_desc": e.type_desc,
                "value": e.value,
            })
        return out

    @classmethod
    def from_json(cls, data: list[dict]) -> Workspace:
        ws = cls()
        for item in data:
            entry = WorkspaceEntry(
                handle=item["handle"],
                value=item.get("value"),
                field_name=item["field_name"],
                tool=item["tool"],
                params=item.get("params", {}),
            )
            entry.type_desc = item.get("type_desc", _type_label(entry.value))
            ws._entries.append(entry)
        return ws

    def _find_entry(self, handle: str) -> WorkspaceEntry | None:
        for entry in self._entries:
            if entry.handle == handle:
                return entry
        return None


# ── Public value descriptor ──


def describe_value(value: Any) -> str:
    """One-line type + structure summary for any Python value.

    The LLM's swiss knife for understanding data: shows types, keys,
    nesting, sizes. Works for handles, user variables, and report entries.

    Examples::

        list[dict], 5 rows — keys: {sid, name, size_bp, topology}
        dict {sequence: {sid, name, size_bp, ...}, features: [{pid, name, type}]}
        str, 5000 chars
        42
    """
    if value is None:
        return "None"
    if isinstance(value, (bool, int, float)):
        return str(value)
    if isinstance(value, str):
        if len(value) <= 40:
            return repr(value)
        return f"str, {len(value)} chars"
    if isinstance(value, list):
        if not value:
            return "list, empty"
        if isinstance(value[0], dict):
            keys = ", ".join(list(value[0].keys())[:8])
            more = ", ..." if len(value[0]) > 8 else ""
            return f"list[dict], {len(value)} rows — keys: {{{keys}{more}}}"
        return f"list[{type(value[0]).__name__}], {len(value)} items"
    if isinstance(value, dict):
        return f"dict {_dict_schema(value)}"
    return type(value).__name__


# ── Internal helpers ──


def _type_label(value: Any) -> str:
    """Short type label for stored metadata."""
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


def _dict_schema(d: dict, max_keys: int = 8) -> str:
    """Dict structure with one level of nested key expansion.

    Shows: {sequence: {sid, name, ...}, features: [{pid, name, type}], count: 42}
    """
    parts: list[str] = []
    for key, val in list(d.items())[:max_keys]:
        if isinstance(val, dict) and val:
            nested = ", ".join(list(val.keys())[:6])
            more = ", ..." if len(val) > 6 else ""
            parts.append(f"{key}: {{{nested}{more}}}")
        elif isinstance(val, list) and val and isinstance(val[0], dict):
            nested = ", ".join(list(val[0].keys())[:6])
            more = ", ..." if len(val[0]) > 6 else ""
            parts.append(f"{key}: [{{{nested}{more}}}]")
        elif isinstance(val, list):
            parts.append(f"{key}: list({len(val)})")
        elif isinstance(val, str):
            if len(val) <= 30:
                parts.append(f"{key}: {repr(val)}")
            else:
                parts.append(f"{key}: str({len(val)})")
        elif isinstance(val, (int, float)):
            parts.append(f"{key}: {val}")
        elif val is None:
            parts.append(f"{key}: None")
        else:
            parts.append(f"{key}: {type(val).__name__}")
    if len(d) > max_keys:
        parts.append("...")
    return "{" + ", ".join(parts) + "}" if parts else "{}"


def _truncate(code: str, max_chars: int = 80) -> str:
    """Truncate code to first line or max_chars, whichever is shorter."""
    first_line = code.strip().split("\n")[0]
    if len(first_line) <= max_chars:
        if "\n" in code.strip():
            return first_line + " ..."
        return first_line
    return first_line[:max_chars] + "..."
