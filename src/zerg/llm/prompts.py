"""LLM prompts for the phased tool-calling flow.

Two modes:
  SIMPLE — 3-step flow: select → execute → summarize (~700 tokens total)
  LOOP   — Agentic loop: LLM chains tools until done (for multi-step queries)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zerg.tools.base import Tool, ToolRegistry

_SELECTION_SYSTEM = """\
You are a tool router for Zerg Browser, a lab sequence search assistant.
Given the user's message, choose a mode and the best tool(s).

MODES:
- SIMPLE: Single tool, direct answer. Use for straightforward queries. (recommended)
- LOOP: Multi-step reasoning with chained tools. Use when the query requires \
extracting data from one tool to feed into another (e.g. "blast the AmpR promoter \
from pUC19" needs extract then blast).

{tool_list}

Reply format (exactly):
MODE: SIMPLE or LOOP
tool1
tool2 (only if LOOP)

Default to SIMPLE unless the query clearly needs multiple steps."""

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

_AGENTIC_SYSTEM = """\
You are Zerg Browser, a lab sequence search assistant.
Call tools as needed to answer the user's question. When done, write a summary.

Guidelines:
- Call ONE tool at a time, wait for the result, then decide next steps.
- Use extract to get feature/primer sequences before running blast, translate, \
digest, gc, revcomp, or transcribe.
- Use features or primers to list what's available on a sequence.
- NEVER fabricate sequences, IDs, or data.
- When you have enough information, respond with a concise natural language summary.

{tool_list}"""

_CHAIN_SUMMARY_SYSTEM = """\
Summarize the results of a multi-step tool chain. The user sees a visual widget \
with the final result data, so focus on the overall narrative, not raw numbers.
Write 1-3 short sentences.{exceeded_note}"""


def build_selection_prompt(registry: ToolRegistry) -> str:
    """Build the tool selection system prompt with grouped tool list."""
    return _SELECTION_SYSTEM.format(tool_list=_format_tool_list(registry))


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


def build_agentic_prompt(registry: ToolRegistry) -> str:
    """Build the agentic loop system prompt with all LLM tools listed."""
    return _AGENTIC_SYSTEM.format(tool_list=_format_tool_list(registry))


def build_chain_summary_prompt(chain_summaries: str, exceeded: bool = False) -> str:
    """Build the final summary prompt for agentic chain results.

    Args:
        chain_summaries: Concatenated summaries from each tool step.
        exceeded: True if the loop hit max turns (prompt LLM to note this).
    """
    note = (
        "\nNote: the analysis was cut short due to step limits. "
        "Summarize what was completed and what remains."
        if exceeded else ""
    )
    return f"{_CHAIN_SUMMARY_SYSTEM.format(exceeded_note=note)}\n\nTool chain results:\n{chain_summaries}"


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
