"""safe_exec -- restricted Python execution with stdout capture."""

from __future__ import annotations

import contextlib
import io
import re
from typing import Any

# Statements blocked at text level before compilation
_BLOCKED_PATTERN = re.compile(
    r"\b(import|__import__|exec|eval|compile|open|globals|locals|vars"
    r"|__builtins__|__subclasses__|__bases__|__mro__|breakpoint|exit|quit)\b"
)

# Whitelisted builtins available inside the sandbox
_SAFE_BUILTINS: dict[str, Any] = {
    # Aggregation
    "len": len,
    "sum": sum,
    "min": min,
    "max": max,
    "abs": abs,
    "round": round,
    "pow": pow,
    # Iteration
    "sorted": sorted,
    "reversed": reversed,
    "enumerate": enumerate,
    "zip": zip,
    "range": range,
    "filter": filter,
    "map": map,
    # Predicates
    "any": any,
    "all": all,
    "isinstance": isinstance,
    # Types
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
    "list": list,
    "dict": dict,
    "tuple": tuple,
    "set": set,
    "frozenset": frozenset,
    "type": type,
    # Misc
    "None": None,
    "True": True,
    "False": False,
    # print is added dynamically to capture stdout
}


def safe_exec(code: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute *code* in a restricted namespace and return the result.

    Parameters
    ----------
    code:
        Python source. Must assign to ``result``.
    variables:
        Extra names injected into the namespace (e.g. cached data handles).

    Returns
    -------
    dict with keys:
        status: "ok" | "error"
        result: the value of ``result`` (on success)
        stdout: captured print output
        type:   "list" | "dict" | "scalar" (on success)
        error:  error message (on failure)
    """
    if not code or not code.strip():
        return {"status": "error", "error": "Empty code", "stdout": ""}

    # Text-level block of dangerous constructs
    if match := _BLOCKED_PATTERN.search(code):
        return {
            "status": "error",
            "error": f"Blocked: '{match.group()}' is not allowed",
            "stdout": "",
        }

    # Build restricted namespace
    stdout_buf = io.StringIO()
    builtins = {**_SAFE_BUILTINS, "print": lambda *a, **kw: print(*a, file=stdout_buf, **kw)}

    namespace: dict[str, Any] = {"__builtins__": builtins}
    if variables:
        namespace.update(variables)

    try:
        compiled = compile(code, "<sandbox>", "exec")
    except SyntaxError as e:
        return {"status": "error", "error": f"SyntaxError: {e}", "stdout": ""}

    try:
        with contextlib.redirect_stdout(stdout_buf):
            exec(compiled, namespace)  # noqa: S102
    except Exception as e:
        return {
            "status": "error",
            "error": f"{type(e).__name__}: {e}",
            "stdout": stdout_buf.getvalue(),
        }

    stdout = stdout_buf.getvalue()

    if "result" not in namespace:
        return {
            "status": "error",
            "error": "Code must assign to `result`",
            "stdout": stdout,
        }

    value = namespace["result"]
    result_type = (
        "list" if isinstance(value, list)
        else "dict" if isinstance(value, dict)
        else "scalar"
    )

    return {"status": "ok", "result": value, "stdout": stdout, "type": result_type}
