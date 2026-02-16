"""Tool router — dispatches user input to the correct tool via LLM or direct invocation."""

import json
import logging
import re
from typing import Any

from zerg.llm.client import LLMClient
from zerg.llm.prompts import build_system_prompt, build_tool_schemas
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

    # ── /help or //help — list available commands ──
    if user_input.strip().lstrip("/") == "help":
        return _help_response(registry)

    # ── Mode 1: Direct — //command ──
    if match := DIRECT_PATTERN.match(user_input):
        tool_name = match.group(1)
        args_text = match.group(2).strip()
        tool = registry.get(tool_name)
        if not tool:
            return _error(f"Unknown tool: {tool_name}")

        # If no args and tool has required params, return a form
        if not args_text:
            schema = tool.input_schema().model_json_schema()
            required = schema.get("required", [])
            if required:
                return {
                    "type": "form",
                    "tool": tool_name,
                    "data": {"schema": schema, "tool_name": tool_name, "description": tool.description},
                    "content": f"Fill in the required parameters for **{tool_name}**:",
                }

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
            "params": params,
            "content": _format_result(tool_name, result, registry),
        }

    # ── Mode 2: Guided — /command ──
    if match := GUIDED_PATTERN.match(user_input):
        tool_name = match.group(1)
        text = match.group(2).strip()
        tool = registry.get(tool_name)
        if not tool:
            return _error(f"Unknown tool: {tool_name}")

        if not llm_client or not tool.use_llm:
            # No LLM or tool opts out — execute directly with parsed args
            params = _parse_args(text)

            # If no args and tool has required params, return a form
            if not text:
                schema = tool.input_schema().model_json_schema()
                required = schema.get("required", [])
                if required:
                    return {
                        "type": "form",
                        "tool": tool_name,
                        "data": {"schema": schema, "tool_name": tool_name, "description": tool.description},
                        "content": f"Fill in the required parameters for **{tool_name}**:",
                    }

            try:
                result = await tool.execute(params)
            except Exception as e:
                return _error(f"Tool error: {e}")
            return {
                "type": "tool_result",
                "tool": tool_name,
                "data": result,
                "params": params,
                "content": _format_result(tool_name, result, registry),
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
    """LLM picks a tool, we execute it, return format_result() + data."""
    tools = build_tool_schemas(registry)

    # Turn 1: user message → LLM picks a tool
    messages = [{"role": "system", "content": build_system_prompt(registry)}]
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
        params = {k: v for k, v in params.items() if v is not None}
        logger.info("LLM tool call: %s(%s)", tool_name, json.dumps(params))
        result = await tool.execute(params)
    except Exception as e:
        logger.error("Tool %s failed: %s", tool_name, e)
        return _error(f"Tool error: {e}")

    # Turn 2: tool result → LLM summarizes (briefly — widget shows the details)
    messages.append({"role": "assistant", "tool_calls": [tool_call]})
    messages.append({
        "role": "tool",
        "tool_call_id": tool_call["id"],
        "content": json.dumps(result),
    })
    messages.append({
        "role": "system",
        "content": (
            "Summarize the tool result in 1-2 short sentences. "
            "The user sees a visual widget with the full data, so do NOT repeat details. "
            "Never output raw JSON or tool call objects."
        ),
    })

    try:
        summary_response = await llm_client.chat(messages)
        summary = summary_response["choices"][0]["message"].get("content", "")
    except Exception as e:
        logger.warning("LLM summary failed: %s", e)
        summary = _format_result(tool_name, result, registry)

    return {
        "type": "tool_result",
        "tool": tool_name,
        "data": result,
        "params": params,
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


def _format_result(tool_name: str, result: dict, registry: ToolRegistry | None = None) -> str:
    """Short summary using the tool's own format_result method."""
    if registry:
        tool = registry.get(tool_name)
        if tool:
            return tool.format_result(result)
    if error := result.get("error"):
        return f"Error: {error}"
    return ""


def _help_response(registry: ToolRegistry) -> dict:
    """Build a help message listing all available commands."""
    lines = ["**Available commands:**\n"]
    for tool in registry.all():
        tag = " *(direct)*" if not tool.use_llm else ""
        lines.append(f"- **/{tool.name}**{tag} — {tool.description}")
    lines.append(f"\nPrefix with `//` for direct execution (no LLM), e.g. `//search ampicillin`.")
    return {"type": "message", "content": "\n".join(lines)}


def _error(msg: str) -> dict:
    return {"type": "message", "content": msg}
