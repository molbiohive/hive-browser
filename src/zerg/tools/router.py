"""Tool router — dispatches user input to the correct tool via LLM or direct invocation."""

import json
import logging
import re
from typing import Any

from zerg.llm.client import LLMClient
from zerg.llm.prompts import SYSTEM_PROMPT, build_tool_schemas
from zerg.tools.base import ToolRegistry

logger = logging.getLogger(__name__)

# Pattern: //command args (direct tool, no LLM)
DIRECT_PATTERN = re.compile(r"^//(\w+)\s*(.*)", re.DOTALL)

# Pattern: /command args (guided, LLM-assisted)
GUIDED_PATTERN = re.compile(r"^/(\w+)\s*(.*)", re.DOTALL)


async def route_input(
    user_input: str,
    registry: ToolRegistry,
    llm_client: LLMClient | None = None,
    history: list[dict] | None = None,
) -> dict[str, Any]:
    """
    Route user input → tool execution → response.

    Three modes:
      //command args → direct tool execution, no LLM
      /command args  → LLM uses the specified tool, then summarizes
      free text      → LLM picks a tool, executes, summarizes
    """

    # ── Mode 1: Direct — //command ──
    if match := DIRECT_PATTERN.match(user_input):
        tool_name = match.group(1)
        args_text = match.group(2).strip()
        tool = registry.get(tool_name)
        if not tool:
            return _error(f"Unknown tool: {tool_name}")

        # Parse args as JSON if provided, otherwise empty
        params = _parse_args(args_text)
        try:
            result = await tool.execute(params)
        except Exception as e:
            logger.error("Tool %s failed: %s", tool_name, e)
            return _error(f"Tool error: {e}")

        return {
            "type": "tool_result",
            "tool": tool_name,
            "data": result,
            "content": _format_result(tool_name, result),
        }

    # ── Mode 2: Guided — /command ──
    if match := GUIDED_PATTERN.match(user_input):
        tool_name = match.group(1)
        text = match.group(2).strip()
        tool = registry.get(tool_name)
        if not tool:
            return _error(f"Unknown tool: {tool_name}")

        if not llm_client:
            # No LLM — try to execute directly with parsed args
            params = _parse_args(text)
            try:
                result = await tool.execute(params)
            except Exception as e:
                return _error(f"Tool error: {e}")
            return {
                "type": "tool_result",
                "tool": tool_name,
                "data": result,
                "content": _format_result(tool_name, result),
            }

        # LLM-assisted: hint it to use this specific tool
        return await _llm_tool_flow(
            user_input=f"Use the {tool_name} tool: {text}" if text else f"Use the {tool_name} tool",
            registry=registry,
            llm_client=llm_client,
            history=history,
        )

    # ── Mode 3: Natural language — LLM picks tool ──
    if not llm_client:
        return _error("LLM not available. Use /command or //command syntax.")

    return await _llm_tool_flow(
        user_input=user_input,
        registry=registry,
        llm_client=llm_client,
        history=history,
    )


async def _llm_tool_flow(
    user_input: str,
    registry: ToolRegistry,
    llm_client: LLMClient,
    history: list[dict] | None = None,
) -> dict[str, Any]:
    """Two-turn LLM flow: pick tool → execute → summarize."""
    tools = build_tool_schemas(registry)

    # Turn 1: user message → LLM picks a tool
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_input})

    try:
        response = await llm_client.chat(messages, tools=tools)
    except Exception as e:
        logger.error("LLM request failed: %s", e)
        return _error(f"LLM unavailable: {e}")

    choice = response["choices"][0]
    msg = choice["message"]

    # If LLM didn't call a tool, return its text directly
    if not msg.get("tool_calls"):
        return {
            "type": "message",
            "content": msg.get("content", "I'm not sure how to help with that."),
        }

    # Execute the tool
    tool_call = msg["tool_calls"][0]
    fn = tool_call["function"]
    tool_name = fn["name"]
    tool = registry.get(tool_name)

    if not tool:
        return _error(f"LLM requested unknown tool: {tool_name}")

    try:
        params = json.loads(fn["arguments"]) if isinstance(fn["arguments"], str) else fn["arguments"]
        result = await tool.execute(params)
    except Exception as e:
        logger.error("Tool %s failed: %s", tool_name, e)
        return _error(f"Tool error: {e}")

    # Turn 2: tool result → LLM summarizes
    messages.append({"role": "assistant", "tool_calls": [tool_call]})
    messages.append({
        "role": "tool",
        "tool_call_id": tool_call["id"],
        "content": json.dumps(result),
    })

    try:
        summary_response = await llm_client.chat(messages)
        summary = summary_response["choices"][0]["message"].get("content", "")
    except Exception as e:
        logger.warning("LLM summary failed: %s", e)
        summary = _format_result(tool_name, result)

    return {
        "type": "tool_result",
        "tool": tool_name,
        "data": result,
        "content": summary,
    }


def _parse_args(text: str) -> dict:
    """Try to parse text as JSON params, fall back to {'query': text}."""
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"query": text}


def _format_result(tool_name: str, result: dict) -> str:
    """Simple text formatting when LLM is not available."""
    if error := result.get("error"):
        return f"Error: {error}"

    if tool_name == "search":
        items = result.get("results", [])
        if not items:
            return f"No results for '{result.get('query', '')}'."
        lines = [f"Found {result.get('total', len(items))} result(s):"]
        for r in items:
            feats = ", ".join(r.get("features", [])[:5])
            lines.append(f"  - {r['name']} ({r['size_bp']} bp, {r['topology']}) [{feats}]")
        return "\n".join(lines)

    if tool_name == "blast":
        hits = result.get("hits", [])
        if not hits:
            return "No BLAST hits found."
        lines = [f"Found {len(hits)} hit(s):"]
        for h in hits:
            lines.append(f"  - {h['subject']}: {h['identity']}% identity, e={h['evalue']}")
        return "\n".join(lines)

    if tool_name == "profile":
        seq = result.get("sequence")
        if not seq:
            return "Sequence not found."
        feats = result.get("features", [])
        lines = [
            f"{seq['name']} — {seq['size_bp']} bp, {seq['topology']}",
            f"Description: {seq.get('description') or 'N/A'}",
            f"Features ({len(feats)}):",
        ]
        for f in feats:
            lines.append(f"  - {f['name']} ({f['type']}) {f['start']}..{f['end']}")
        return "\n".join(lines)

    if tool_name == "status":
        lines = [
            f"Indexed files: {result.get('indexed_files', 0)}",
            f"Sequences: {result.get('sequences', 0)}",
            f"Features: {result.get('features', 0)}",
            f"Primers: {result.get('primers', 0)}",
            f"Database: {'connected' if result.get('database_connected') else 'disconnected'}",
            f"LLM: {'available' if result.get('llm_available') else 'unavailable'}",
        ]
        return "\n".join(lines)

    if tool_name == "browse":
        entries = result.get("entries", [])
        if not entries:
            return f"Empty directory: {result.get('path', '/')}"
        lines = [f"Directory: {result.get('path', '/')}"]
        for e in entries:
            if e.get("is_dir"):
                lines.append(f"  [dir] {e['name']}/")
            else:
                status = " [indexed]" if e.get("indexed") else ""
                lines.append(f"  {e['name']} ({e.get('size', 0)} bytes){status}")
        return "\n".join(lines)

    return json.dumps(result, indent=2)


def _error(msg: str) -> dict:
    return {"type": "message", "content": msg}
