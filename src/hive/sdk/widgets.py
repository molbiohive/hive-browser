"""Widget result formatting helpers for external tools.

Each function formats a result dict for a specific widget type.
Internal widgets (blast, profile, status, model) are handled
by their respective internal tools directly.
"""

from typing import Any


def table(rows: list[dict], query: str = "") -> dict[str, Any]:
    """Format result for the table widget (widget='table').

    Args:
        rows: List of result dicts with fields like name, size_bp, etc.
        query: The search query string.
    """
    return {"results": rows, "total": len(rows), "query": query}


def text(message: str) -> dict[str, Any]:
    """Format result for text-only display (widget='text').

    The message is shown in the chat bubble. No dedicated widget renders.
    """
    return {"content": message}
