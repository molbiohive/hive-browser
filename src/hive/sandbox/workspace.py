"""Workspace -- per-loop variable store and LLM context hub."""

from __future__ import annotations

from typing import Any


class Workspace:
    """Central data context for the LLM agent.

    Holds two kinds of data:
      - **User variables** -- Python variables persisted across sandbox calls.
      - **Step history** -- compact log of what the LLM has done.

    Two methods produce all LLM-facing context:
      - ``describe()`` -- current scope (what data exists and how to access it).
      - ``history()``  -- progress (what was done and what happened).
    """

    def __init__(self):
        self._user_vars: dict[str, Any] = {}
        self._steps: list[dict] = []
        self._desc_results: list[tuple[str, str]] = []

    # -- User variables (persisted across sandbox calls within a message) --

    @property
    def user_vars(self) -> dict[str, Any]:
        return self._user_vars

    def update_vars(self, new_vars: dict[str, Any]) -> None:
        self._user_vars.update(new_vars)

    # -- Step tracking --

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

    # -- LLM context: describe() + history() --

    def describe(
        self,
        report: dict[str, Any] | None = None,
        tool_signatures: list[str] | None = None,
    ) -> str:
        """Python-comment style scope -- everything the LLM can access.

        Groups: user variables -> report -> desc() results -> available commands.
        """
        lines: list[str] = []

        # User variables from previous python calls
        for name in sorted(self._user_vars):
            val = self._user_vars[name]
            lines.append(f"# {name}: {_value_shape(val)}")
            for detail_line in _render_value(name, val):
                lines.append(f"#   {detail_line}")

        # Report entries (sandbox report dict)
        if report:
            for key, val in report.items():
                rname = f'report["{key}"]'
                lines.append(f"# {rname}: {_value_shape(val)}")
                for detail_line in _render_value(rname, val):
                    lines.append(f"#   {detail_line}")

        # Pending desc() results
        if self._desc_results:
            lines.append("#")
            for var_name, detail in self._desc_results:
                lines.append(f"# desc({var_name}):")
                for dl in detail.split("\n"):
                    lines.append(f"#   {dl}")
            self._desc_results.clear()

        # Available tools
        if tool_signatures:
            lines.append("#")
            lines.append("# [tools]")
            for sig in tool_signatures:
                lines.append(f"# {sig}")

        return "\n".join(lines) if lines else "Empty."

    def add_desc_result(self, var_name: str, detail: str) -> None:
        """Record a desc() result to be shown in the next describe()."""
        self._desc_results.append((var_name, detail))

    def history(self, max_steps: int = 8) -> str:
        """Compact progress log -- ok/x prefixed lines with code context."""
        if not self._steps:
            return ""
        recent = self._steps[-max_steps:]
        lines: list[str] = []
        offset = len(self._steps) - len(recent)
        if offset > 0:
            lines.append(f"# ({offset} earlier steps omitted)")
        for s in recent:
            code = s.get("code")
            code_ctx = f" `{_truncate(code, 80)}`:" if code else ""
            if s["error"]:
                err = _truncate(s["error"], 60)
                hint = f" -- {s['hint']}" if s.get("hint") else ""
                lines.append(f"# x: {s['tool']}{code_ctx} {err}{hint}")
            else:
                produced = s.get("produced")
                if produced:
                    lines.append(f"# ok: {s['tool']}{code_ctx} -> {produced}")
                else:
                    fb = _truncate(s["feedback"], 80)
                    lines.append(f"# ok: {s['tool']}{code_ctx} -> {fb}")
        return "\n".join(lines)

    # -- Lifecycle --

    def reset_loop(self) -> None:
        """Clear per-message state (user variables, step history)."""
        self._user_vars.clear()
        self._steps.clear()


# -- Public value descriptor --


def describe_value(value: Any) -> str:
    """One-line type + structure summary for any Python value."""
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
            return f"list[dict], {len(value)} rows, keys: {{{keys}{more}}}"
        return f"list[{type(value[0]).__name__}], {len(value)} items"
    if isinstance(value, dict):
        return f"dict {_dict_schema(value)}"
    return type(value).__name__


# -- Internal helpers --


def _dict_schema(d: dict, max_keys: int = 8) -> str:
    """Dict structure with one level of nested key expansion."""
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


def _value_shape(value: Any) -> str:
    """Python-style type annotation for a value."""
    if value is None:
        return "None"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return f"int = {value}"
    if isinstance(value, float):
        return f"float = {value}"
    if isinstance(value, str):
        if len(value) <= 40:
            return f"str = {repr(value)}"
        return f"str  # {len(value)} chars"
    if isinstance(value, list):
        if not value:
            return "list  # empty"
        if isinstance(value[0], dict):
            keys = ", ".join(list(value[0].keys())[:6])
            more = ", ..." if len(value[0]) > 6 else ""
            return f"list[dict]  # {len(value)} rows, keys: {{{keys}{more}}}"
        return f"list[{type(value[0]).__name__}]  # {len(value)} items"
    if isinstance(value, dict):
        keys = ", ".join(list(value.keys())[:8])
        more = ", ..." if len(value) > 8 else ""
        return f"dict  # keys: {{{keys}{more}}}"
    return type(value).__name__


def _render_value(handle: str, value: Any) -> list[str]:
    """Rich multi-line rendering of a value for describe()."""
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
            return f"[{{...}}, ...+{len(val) - 1}]" if len(val) > 1 else "[{...}]"
        return f"list({len(val)})"
    if isinstance(val, dict):
        return f"dict({len(val)})"
    return type(val).__name__


def detailed_describe(value: Any) -> str:
    """Detailed inspection for desc() builtin."""
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
