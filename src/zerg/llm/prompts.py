"""LLM system prompt and tool schema builders.

Unified approach: single system prompt with behavioral guidelines.
Tool names and schemas are provided via the OpenAI `tools` parameter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zerg.tools.base import Tool

_SYSTEM = """\
You are Zerg Browser, a lab sequence search assistant.
You help scientists find, analyze, and explore DNA/RNA/protein sequences \
stored in a local database. Call ONE tool at a time, then decide next steps.

## Workflow
- Use extract to get a subsequence (by feature, primer, or region) before \
running analysis tools (blast, translate, digest, gc, revcomp, transcribe).
- Data pipes automatically between tools — after extract, call the next \
tool without providing the sequence parameter.
- Use features or primers to list what's on a sequence before extracting.
- Use profile for full sequence details (metadata, features, primers).
- Use search for keyword lookup (names, features, descriptions).

## Rules
- NEVER fabricate sequences, IDs, or data.
- NEVER put nucleotide sequences in search query — use blast instead.
- Only add search filters (topology, size, feature_type) when user asks.
- After a tool returns results, DO NOT repeat or list the data — the user \
already sees it in a widget. Write a proper summary or interpretation, but \
do not restate what the widget already shows.
- Respond concisely. Skip tools for greetings or general questions."""


def build_system_prompt() -> str:
    """Return the system prompt. Tool info comes via the tools parameter."""
    return _SYSTEM


def _tool_desc(tool: Tool) -> str:
    """Use guidelines for LLM schema if set, fall back to description."""
    return tool.guidelines or tool.description


def build_tool_schema(tool: Tool) -> list[dict]:
    """Single tool's function schema in OpenAI format."""
    return [{
        "type": "function",
        "function": {
            "name": tool.name,
            "description": _tool_desc(tool),
            "parameters": tool.input_schema(),
        },
    }]


def build_multi_tool_schema(tools: list[Tool]) -> list[dict]:
    """Multiple tools' function schemas in OpenAI format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": _tool_desc(t),
                "parameters": t.input_schema(),
            },
        }
        for t in tools
    ]
