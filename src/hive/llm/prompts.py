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
- PID = Part ID (individual feature/primer). Parts are canonical -- same sequence \
across files shares the same PID.
- Use the parts tool with pid to look up a part, or with sid to list parts on a sequence.
- All sequence-accepting tools accept: raw sequence, sid:N, or pid:N -- automatically resolved.

## Workflow
- For simple queries: call search, blast, or profile directly.
- For multi-step analysis: use python with callable tools:
    results = search(query="KanR")
    pids = [p["pid"] for p in results["parts"] if p["type"] == "CDS" and p["length"] > 500]
    gc_data = [gc(sequence=f"pid:{{pid}}") for pid in pids[:15]]
    report["analysis"] = gc_data
    feedback = f"Analyzed {{len(pids)}} KanR CDS parts"
- Tool calls from python auto-store results in workspace as handles.
- python is always available -- use it even without prior tool calls.
- search returns BOTH sequences (SIDs) AND parts (PIDs). Use the parts section \
when the user asks about features/parts.

## Rules
- NEVER fabricate sequences, IDs, or data. Use blast for sequence lookup, not search.
- NEVER answer questions about data visible in the workspace without using python first.
- Use sid or pid (integers) for follow-up tools. Never use name when an ID is available. \
Prefer pid when the user asks about parts/features, sid when asking about whole sequences.
- After tool results, write 1-2 sentences of interpretation. \
NEVER list or restate individual items -- the user sees a rich widget.
- Respond concisely.

## Workspace & Report
- ALL tool results are stored in workspace as r0, r1, r2, etc.
- Tool calls from python code also auto-store results in workspace.
- Workspace persists across messages. Data from earlier turns is available via the same handles.
- Scalar values (counts, percentages) are shown inline in the descriptor.
- Use python(code="...") to query workspace and build output.
- Must assign `feedback` -- a short caption for the user (e.g. "Found 5 CDS features").
- `report` dict accumulates widget data across python calls:
  Tables: report["features"] = [{{...}}, ...] (each list[dict] = a table tab).
  Sequences: report["protein"] = "MKLIV..." (long strings = copyable blocks).
  Scalars: report["gc"] = 52.3 (shown in header row).
- Variables you create in python calls persist across calls within the same message.
- Available: len, sum, min, max, sorted, filter, map, comprehensions. No imports.

## Structured Output
For complex queries, accumulate data in `report` across multiple python calls. \
Mix tool calls and python freely: tool -> python(store to report) -> tool -> python(add more).
For simple queries, answer concisely in text without using report."""


def build_system_prompt() -> str:
    """Return the system prompt. Tool info comes via the tools parameter."""
    return _SYSTEM


def _tool_desc(tool: Tool) -> str:
    """Use guidelines for LLM schema if set, fall back to description."""
    return tool.guidelines or tool.description


def _slim_schema(schema: dict) -> dict:
    """Strip Pydantic bloat from a JSON Schema for minimal token usage.

    - Removes ``title`` keys (redundant with property names)
    - Flattens ``anyOf: [{type: X}, {type: null}]`` to ``{type: X}``
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


def build_tool_schema(tools: list[Tool]) -> list[dict]:
    """Build function schemas in OpenAI format (uses slim LLM schemas)."""
    schemas = []
    for t in tools:
        params = _slim_schema(t.llm_schema())
        schemas.append({
            "type": "function",
            "function": {
                "name": t.name,
                "description": _tool_desc(t),
                "parameters": params,
            },
        })
    return schemas


# ── Planning prompt (used by Planner) ──

_PLAN_SYSTEM = """\
You are a planning assistant for a lab sequence browser.

Available tools:
{catalog}

Write a brief task description (1-2 sentences) for the worker LLM.
Do NOT answer the user directly. Just describe what needs to be done.
- For data questions: which operations to perform and what to look for.
- For greetings/chat/general questions: "respond conversationally".
- NEVER fabricate data, IDs, or results."""


def build_tool_catalog(tools: list[Tool]) -> str:
    """One-liner-per-tool catalog for the planning prompt (~20 tokens/tool).

    Uses the short ``description`` (not verbose ``guidelines``) to keep
    the planning call cheap.
    """
    return "\n".join(f"- {t.name}: {t.description}" for t in tools)


def build_plan_messages(
    catalog: str,
    user_input: str,
    history: list[dict] | None = None,
) -> list[dict]:
    """Build message list for the planning LLM call."""
    system = _PLAN_SYSTEM.format(catalog=catalog)
    messages: list[dict] = [{"role": "system", "content": system}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_input})
    return messages
