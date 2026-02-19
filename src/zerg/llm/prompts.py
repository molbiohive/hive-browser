"""LLM prompts for the phased tool-calling flow.

Three-step flow:
  1. Selection — LLM picks 1-3 tool names from grouped list (~200 tokens)
  2. Execution — LLM extracts params using only the selected tool's schema (~300 tokens)
  3. Summary  — LLM writes 1-2 sentence summary from compact stats (~200 tokens)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zerg.tools.base import Tool, ToolRegistry

_SELECTION_SYSTEM = """\
You are a tool router for Zerg Browser, a lab sequence search assistant.
Given the user's message, pick the best tool(s) from the list below.

{tool_list}

Reply with 1-3 tool names, one per line. Nothing else."""

_EXECUTION_SYSTEM = """\
You are Zerg Browser, a lab sequence search assistant.
Use the `{tool_name}` tool. Extract parameters from the user's message.
{guidelines}
- Call exactly ONE tool.
- NEVER fabricate sequences, IDs, file paths, or data.
- NEVER put nucleotide sequences in search `query` — use blast instead."""

_SUMMARY_SYSTEM = """\
Summarize the tool result in 1-2 short sentences.
The user sees a visual widget with the full data, so do NOT repeat individual \
results or table rows. Never output raw JSON or tool call objects."""


def build_selection_prompt(registry: ToolRegistry) -> str:
    """Build the tool selection system prompt with grouped tool list."""
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

    return _SELECTION_SYSTEM.format(tool_list="\n".join(lines).strip())


def build_execution_prompt(tool: Tool) -> str:
    """Build the execution system prompt with tool name and guidelines."""
    guidelines = f"\n{tool.guidelines}" if tool.guidelines else ""
    return _EXECUTION_SYSTEM.format(tool_name=tool.name, guidelines=guidelines)


def build_summary_prompt(tool_summary: str) -> str:
    """Build the summary system prompt with compact tool result data.

    Args:
        tool_summary: Output from tool.summary_for_llm(result) — already compact.
                      Truncation is handled by _auto_summarize in base.py,
                      not here.
    """
    return f"{_SUMMARY_SYSTEM}\n\nTool result data:\n{tool_summary}"


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
