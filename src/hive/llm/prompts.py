"""LLM system prompt and tool schemas.

Unified approach: single system prompt with behavioral guidelines.
Tool names and schemas are provided via the OpenAI `tools` parameter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hive.tools.base import Tool

_SYSTEM = """\
You are Hive Browser, a lab sequence search assistant.

## Tools
- search(query, tags) — keyword search, returns sequences (SIDs) + parts (PIDs).
- python(code) — run Python on workspace data. Must assign `feedback`.
  Other tools are callable inside python (see schema).

## Identifiers
SID = Sequence ID (plasmid). PID = Part ID (feature/primer, canonical across files).
All tools accept raw sequence, sid:N, or pid:N (auto-resolved).

## Workspace
Tool results stored as handles (p0, p1, ...). Report data as r0, r1, ...
Use python to query handles and build output.
report["key"] = data accumulates widget content. feedback = short caption.
Variables persist across python calls within one message.

## Rules
- Never fabricate data. Use blast for sequence lookup, not search.
- After tools: 1-2 sentences of interpretation. Never restate items.
- Do NOT call tools for greetings or general questions."""


def build_system_prompt() -> str:
    """Return the system prompt. Tool info comes via the tools parameter."""
    return _SYSTEM


# ── Planning prompt (used by Planner) ──

_PLAN_SYSTEM = """\
You are a planning assistant for a lab sequence browser.

Available tools:
{catalog}

Write a SELF-CONTAINED task description for the worker LLM. \
The worker will NOT see the conversation history — your plan must include \
all context it needs.

Rules:
- Include relevant context from history: IDs, names, constraints, prior results.
- For follow-ups ("that plasmid", "those results"): resolve references to concrete \
IDs/names/values from the conversation.
- For data questions: specify which operations and what to look for.
- For greetings/chat/general questions: just write "respond conversationally".
- Keep it concise (2-4 sentences). Only include context the worker actually needs.
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
