"""LLM system prompt and tool schema builders.

Unified approach: single system prompt with all tools.
The LLM decides whether to call tools or respond conversationally.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zerg.tools.base import Tool, ToolRegistry

_SYSTEM = """\
You are Zerg Browser, a lab sequence search assistant.
You help scientists find, analyze, and explore DNA/RNA/protein sequences.
You can use tools to answer questions. Call ONE tool at a time, wait for the \
result, then decide next steps or respond to the user.

Guidelines:
- Use extract to get sequences before running blast, translate, digest, gc, \
revcomp, or transcribe. Extract with just sequence_name for the full sequence.
- Use features or primers to list what's available on a sequence.
- Data flows automatically between tools — after extract, just call the next \
analysis tool without providing the sequence parameter. It will be injected.
- NEVER fabricate sequences, IDs, file paths, or data.
- NEVER put nucleotide sequences in search `query` — use blast instead.
- When you have enough information, respond with a concise natural language answer.
- For simple greetings or questions, respond directly without calling tools.

{tool_list}"""


def build_system_prompt(registry: ToolRegistry) -> str:
    """Build the unified system prompt with all LLM tools listed."""
    return _SYSTEM.format(tool_list=_format_tool_list(registry))


def build_tool_schema(tool: Tool) -> list[dict]:
    """Single tool's function schema in OpenAI format."""
    return [{
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
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
                "description": t.description,
                "parameters": t.input_schema(),
            },
        }
        for t in tools
    ]


def _format_tool_list(registry: ToolRegistry) -> str:
    """Format LLM tools into grouped text list."""
    tools = registry.llm_tools()
    groups: dict[str | None, list[Tool]] = {}
    for t in tools:
        g = t.group()
        groups.setdefault(g, []).append(t)

    lines = []
    for group_name, group_tools in groups.items():
        header = f"## {group_name}" if group_name else "## general"
        lines.append(header)
        for t in group_tools:
            lines.append(f"- {t.name}: {t.description}")
        lines.append("")

    return "\n".join(lines).strip()
