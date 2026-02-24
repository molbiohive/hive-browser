"""LLM system prompt and tool schema builders.

Unified approach: single system prompt with behavioral guidelines.
Tool names and schemas are provided via the OpenAI `tools` parameter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hive.tools.base import Tool

_SYSTEM = """\
You are Hive Browser, a lab sequence search assistant.
You help scientists find, analyze, and explore DNA/RNA/protein sequences \
stored in a local database.

## CRITICAL: When NOT to call tools
Do NOT call any tool when the user:
- Greets you, asks "who are you", or makes small talk — just reply in text.
- Asks a general knowledge question — answer from your knowledge.
- Asks about your capabilities — describe them in text.
- Asks a follow-up about previous results — answer from context.
Only call a tool when the user explicitly asks to search, analyze, or \
retrieve sequence data.

## Workflow (only when tools are needed)
- Call ONE tool at a time, then decide next steps.
- Use extract to get a subsequence (by feature, primer, or region) before \
running analysis tools (blast, translate, digest, gc, revcomp, transcribe).
- Data pipes automatically between tools — after extract, call the next \
tool without providing the sequence parameter.
- Use features or primers to list what's on a sequence before extracting.
- Use profile for full sequence details (metadata, features, primers).
- Use search for keyword lookup (names, features, descriptions, directory tags).
- If the user mentions a project, folder, or directory context, pass it in the search tags parameter.

## Rules
- NEVER fabricate sequences, IDs, or data.
- NEVER put nucleotide sequences in search query — use blast instead.
- Only add search filters (topology, size, feature_type) when user asks.
- After a tool returns results, the user sees a rich table/widget with full \
data. NEVER list, enumerate, or restate individual items from the results. \
Instead write 1-2 sentences of interpretation or context. Bad: "Here are \
the results: 1. pUC19 2. pET28a ...". Good: "Found 5 kanamycin-resistant \
plasmids, mostly cloning vectors."
- Respond concisely."""


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
