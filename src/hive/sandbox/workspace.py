"""Workspace -- per-loop data store and LLM context hub."""

from __future__ import annotations

from typing import Any


class WorkspaceEntry:
    """Single stored value with metadata."""

    __slots__ = ("handle", "value", "field_name", "tool", "params", "type_desc", "call_repr")

    def __init__(
        self,
        handle: str,
        value: Any,
        field_name: str,
        tool: str,
        params: dict[str, Any],
        call_repr: str = "",
    ):
        self.handle = handle
        self.value = value
        self.field_name = field_name
        self.tool = tool
        self.params = params
        self.type_desc = _type_label(value)
        self.call_repr = call_repr


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
        self._desc_results: list[tuple[str, str]] = []

    # ── Core storage ──

    def store(
        self, key: str, value: Any, tool: str, params: dict[str, Any] | None = None,
        prefix: str = "p", call_repr: str = "",
    ) -> str:
        """Store *value* under field name *key*, return handle."""
        count = sum(1 for e in self._entries if e.handle.startswith(prefix))
        handle = f"{prefix}{count}"
        self._entries.append(
            WorkspaceEntry(handle, value, key, tool, params or {}, call_repr=call_repr)
        )
        return handle

    def get(self, handle: str) -> Any | None:
        entry = self._find_entry(handle)
        return entry.value if entry else None

    def store_result(
        self,
        result: dict[str, Any],
        tool: str,
        params: dict[str, Any] | None = None,
        call_repr: str = "",
    ) -> str:
        """Store tool result as a single handle. Returns the handle name."""
        return self.store("_result", result, tool, params or {}, call_repr=call_repr)

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
        produced: str | None = None, hint: str | None = None,
    ) -> None:
        self._steps.append({
            "tool": tool, "feedback": feedback, "code": code, "error": error,
            "produced": produced, "hint": hint,
        })

    @property
    def steps(self) -> list[dict]:
        return self._steps

    # ── LLM context: describe() + history() ──

    def describe(
        self,
        report: dict[str, Any] | None = None,
        tool_signatures: list[str] | None = None,
    ) -> str:
        """Python-comment style scope — everything the LLM can access.

        Groups: pipeline handles → user variables → report →
        persistent handles → desc() results → available commands.

        """
        lines: list[str] = []

        def _emit_entries(prefix: str) -> None:
            for e in self._entries:
                if not e.handle.startswith(prefix):
                    continue
                lines.append(_handle_line(e))
                for detail_line in _render_value(e.handle, e.value):
                    lines.append(f"#   {detail_line}")

        # Pipeline handles (current message)
        _emit_entries("p")

        # User variables from previous python calls
        for name in sorted(self._user_vars):
            val = self._user_vars[name]
            lines.append(f"# {name} -- {_value_shape(val)}")

        # Report entries (sandbox report dict)
        if report:
            for key, val in report.items():
                lines.append(f'# report["{key}"] -- {_value_shape(val)}')

        # Persistent handles from previous messages
        _emit_entries("r")

        # Pending desc() results
        if self._desc_results:
            lines.append("#")
            for var_name, detail in self._desc_results:
                lines.append(f"# desc({var_name}):")
                for dl in detail.split("\n"):
                    lines.append(f"#   {dl}")
            self._desc_results.clear()

        # Available commands — one per line
        if tool_signatures:
            lines.append("#")
            for sig in tool_signatures:
                lines.append(f"# {sig}")

        return "\n".join(lines) if lines else "Empty."

    def add_desc_result(self, var_name: str, detail: str) -> None:
        """Record a desc() result to be shown in the next describe()."""
        self._desc_results.append((var_name, detail))

    def history(self, max_steps: int = 5) -> str:
        """Compact progress log — ok/x prefixed lines.

        Format::

          # ok: search(query="KanR") -> p0 (56 rows)
          # ok: python -> filtered 3 items
          # x: python KeyError 'gc_content' -- keys: {sid, name, size_bp}
        """
        if not self._steps:
            return ""
        recent = self._steps[-max_steps:]
        lines: list[str] = []
        offset = len(self._steps) - len(recent)
        if offset > 0:
            lines.append(f"# ({offset} earlier steps omitted)")
        for s in recent:
            if s["error"]:
                err = _truncate(s["error"], 60)
                hint = f" -- {s['hint']}" if s.get("hint") else ""
                lines.append(f"# x: {s['tool']} {err}{hint}")
            else:
                produced = s.get("produced")
                if produced:
                    lines.append(f"# ok: {s['tool']} -> {produced}")
                else:
                    fb = _truncate(s["feedback"], 80)
                    lines.append(f"# ok: {s['tool']} -> {fb}")
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
            d = {
                "handle": e.handle,
                "field_name": e.field_name,
                "tool": e.tool,
                "params": e.params,
                "type_desc": e.type_desc,
                "value": e.value,
            }
            if e.call_repr:
                d["call_repr"] = e.call_repr
            out.append(d)
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
                call_repr=item.get("call_repr", ""),
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


def _handle_line(e: WorkspaceEntry) -> str:
    """One-line Python-comment header for a workspace handle."""
    shape = _value_shape(e.value)
    if e.call_repr:
        return f"# {e.handle} = {e.call_repr} -> {shape}"
    return f"# {e.handle} -- {shape}"


def _value_shape(value: Any) -> str:
    """Compact shape: '56 rows', 'dict', 'str(5369)', etc."""
    if value is None:
        return "None"
    if isinstance(value, (bool, int, float)):
        return str(value)
    if isinstance(value, str):
        return repr(value) if len(value) <= 40 else f"str({len(value)})"
    if isinstance(value, list):
        if not value:
            return "empty list"
        if isinstance(value[0], dict):
            return f"{len(value)} rows"
        return f"list({len(value)})"
    if isinstance(value, dict):
        return "dict"
    return type(value).__name__


def _render_value(handle: str, value: Any) -> list[str]:
    """Rich multi-line rendering of a value for describe().

    dict: JSON-like with nested expansion — every key visible.
    list[dict]: first row expanded inline.
    Other: nothing (shape in header is enough).
    """
    if isinstance(value, dict) and value:
        return _render_dict(handle, value)
    if isinstance(value, list) and value and isinstance(value[0], dict):
        row_str = _flat_dict(value[0])
        return [f"{handle}[0] = {row_str}"]
    return []


def _render_dict(handle: str, d: dict) -> list[str]:
    """Multi-line dict rendering with nested list/dict expansion."""
    lines: list[str] = [f"{handle} = {{"]
    items = list(d.items())
    for i, (k, v) in enumerate(items):
        comma = "," if i < len(items) - 1 else ""
        lines.append(f"  {k}: {_rich_val(v)}{comma}")
    lines.append("}")
    return lines


def _rich_val(val: Any) -> str:
    """Value repr with nested expansion for dicts/lists."""
    if val is None:
        return "None"
    if isinstance(val, bool):
        return str(val)
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, str):
        return repr(val) if len(val) <= 30 else f"str({len(val)})"
    if isinstance(val, list):
        if not val:
            return "[]"
        if isinstance(val[0], dict):
            row = _flat_dict(val[0])
            if len(val) == 1:
                return f"[{row}]"
            return f"[{row}, ...+{len(val) - 1}]"
        if len(val) <= 5:
            return repr(val)
        return f"[{repr(val[0])}, ...+{len(val) - 1}]"
    if isinstance(val, dict):
        return _flat_dict(val)
    return type(val).__name__


def _flat_dict(d: dict, max_keys: int = 8) -> str:
    """Single-line {key: val, ...} with truncated values."""
    parts: list[str] = []
    for key, val in list(d.items())[:max_keys]:
        parts.append(f"{key}: {_short_val(val)}")
    if len(d) > max_keys:
        parts.append("...")
    return "{" + ", ".join(parts) + "}"


def _short_val(val: Any, max_len: int = 20) -> str:
    """Truncated value repr for inline display."""
    if val is None:
        return "None"
    if isinstance(val, bool):
        return str(val)
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, str):
        return repr(val) if len(val) <= max_len else f"str({len(val)})"
    if isinstance(val, list):
        if not val:
            return "[]"
        if isinstance(val[0], dict):
            return f"[{{...}}, ...+{len(val) - 1}]" if len(val) > 1 else f"[{{...}}]"
        return f"list({len(val)})"
    if isinstance(val, dict):
        return f"dict({len(val)})"
    return type(val).__name__


def detailed_describe(value: Any) -> str:
    """Detailed inspection for desc() builtin.

    list[dict]: column types + first 3 example rows.
    dict: full key expansion.
    Other: repr truncated.
    """
    if isinstance(value, list) and value and isinstance(value[0], dict):
        row = value[0]
        col_types = ", ".join(f"{k}: {type(v).__name__}" for k, v in row.items())
        lines = [f"{len(value)} rows -- {{{col_types}}}"]
        for i, r in enumerate(value[:3]):
            lines.append(f"[{i}] = {_flat_dict(r, max_keys=10)}")
        if len(value) > 3:
            lines.append(f"... ({len(value) - 3} more)")
        return "\n".join(lines)
    if isinstance(value, dict):
        lines = ["{"]
        for k, v in value.items():
            lines.append(f"  {k}: {_rich_val(v)},")
        lines.append("}")
        return "\n".join(lines)
    r = repr(value)
    return r[:200] + "..." if len(r) > 200 else r


def _truncate(text: str, max_chars: int = 80) -> str:
    """Truncate to first line or max_chars, whichever is shorter."""
    first_line = text.strip().split("\n")[0]
    if len(first_line) <= max_chars:
        if "\n" in text.strip():
            return first_line + " ..."
        return first_line
    return first_line[:max_chars] + "..."
