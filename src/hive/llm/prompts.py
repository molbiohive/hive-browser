"""LLM system prompt and tool schema builders.

Unified approach: single system prompt with behavioral guidelines.
Tool names and schemas are provided via the OpenAI `tools` parameter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hive.tools.base import Tool

_SYSTEM = """\
You are Hive Browser, a lab sequence search assistant for DNA/RNA/protein \
sequences in a local database.

Do NOT call tools for greetings, general knowledge, capability questions, \
or follow-ups about previous results. Only call tools for sequence data operations.

## Identifiers
- SID = Sequence ID (whole plasmid/construct). Use for sequence operations.
- PID = Part ID (individual feature/primer). Parts are canonical — same sequence \
across files shares the same PID.
- Use the parts tool with pid to look up a part, or with sid to list parts on a sequence.
- All sequence-accepting tools (blast, translate, digest, gc, revcomp, transcribe) accept: \
raw sequence, sid:N, or pid:N — automatically resolved.

## Workflow
- ONE tool per turn. Data pipes automatically between tools.
- If user names a sequence/SID and feature, go directly to extract. \
Do NOT search or list features first.
- extract before analysis tools (blast, translate, digest, gc, revcomp, transcribe). \
Or pass sid:N / pid:N directly to skip extract.
- search returns BOTH sequences (SIDs) AND parts (PIDs). Use the parts section \
when the user asks about features/parts — pass PIDs directly to align, blast, etc. \
Do NOT call the parts tool on individual sequences when search already returned parts.
- For alignment of parts: search → collect PIDs from parts results → align with pids.

## Rules
- NEVER fabricate sequences, IDs, or data. Use blast for sequence lookup, not search.
- Use sid or pid (integers) for follow-up tools. Never use name when an ID is available. \
Prefer pid when the user asks about parts/features, sid when asking about whole sequences.
- After tool results, write 1-2 sentences of interpretation. \
NEVER list or restate individual items -- the user sees a rich widget.
- Respond concisely."""


def build_system_prompt() -> str:
    """Return the system prompt. Tool info comes via the tools parameter."""
    return _SYSTEM


def _tool_desc(tool: Tool) -> str:
    """Use guidelines for LLM schema if set, fall back to description."""
    return tool.guidelines or tool.description


def _slim_schema(schema: dict) -> dict:
    """Strip Pydantic bloat from a JSON Schema for minimal token usage.

    - Removes ``title`` keys (redundant with property names)
    - Flattens ``anyOf: [{type: X}, {type: null}]`` → ``{type: X}``
    - Removes ``default: null``
    """
    schema = {k: v for k, v in schema.items() if k != "title"}
    if "properties" in schema:
        slim_props = {}
        for name, prop in schema["properties"].items():
            prop = {k: v for k, v in prop.items() if k != "title"}
            # Flatten anyOf with null
            if "anyOf" in prop:
                types = [t for t in prop["anyOf"] if t.get("type") != "null"]
                if len(types) == 1:
                    prop = {**prop, **types[0]}
                    del prop["anyOf"]
            # Remove default: null
            if prop.get("default") is None and "default" in prop:
                del prop["default"]
            slim_props[name] = prop
        schema["properties"] = slim_props
    return schema


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
    """Multiple tools' function schemas in OpenAI format (uses slim LLM schemas)."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": _tool_desc(t),
                "parameters": _slim_schema(t.llm_schema()),
            },
        }
        for t in tools
    ]
