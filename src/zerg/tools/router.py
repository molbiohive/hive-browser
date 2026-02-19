"""Tool router — dispatches user input to the correct tool via LLM or direct invocation."""

import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from zerg.llm.client import LLMClient
from zerg.llm.prompts import build_multi_tool_schema, build_system_prompt
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
    max_turns: int = 5,
    pipe_min_length: int = 200,
    on_progress: Callable[[dict], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    """
    Route user input → tool execution → response.

    Three modes:
      //command args → direct tool execution, no LLM
      /command args  → LLM extracts params for specified tool, then summarizes
      free text      → unified agentic loop (LLM picks tools, chains, converses)
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
            schema = tool.input_schema()
            if schema.get("required"):
                return _form_response(tool_name, tool.description, schema)

        params = _parse_args(args_text)
        try:
            result = await tool.execute(params)
        except Exception as e:
            logger.error("Tool %s failed: %s", tool_name, e)
            return _error(f"Tool error: {e}")

        return _tool_response(tool_name, result, params, tool.format_result(result))

    # ── Mode 2: Guided — /command ──
    if match := GUIDED_PATTERN.match(user_input):
        tool_name = match.group(1)
        text = match.group(2).strip()
        tool = registry.get(tool_name)
        if not tool:
            return _error(f"Unknown tool: {tool_name}")

        if not llm_client or "llm" not in tool.tags:
            # No LLM or tool opts out — execute directly
            if not text:
                schema = tool.input_schema()
                if schema.get("required"):
                    return _form_response(tool_name, tool.description, schema)

            params = _parse_args(text)
            try:
                result = await tool.execute(params)
            except Exception as e:
                return _error(f"Tool error: {e}")
            return _tool_response(tool_name, result, params, tool.format_result(result))

        # LLM-assisted: run through unified loop with tool hint
        prompt = f"Use the {tool_name} tool: {text}" if text else f"Use the {tool_name} tool"
        return await _unified_loop(
            user_input=prompt,
            registry=registry,
            llm_client=llm_client,
            history=history,
            max_turns=max_turns,
            pipe_min_length=pipe_min_length,
            on_progress=on_progress,
        )

    # ── Mode 3: Natural language — unified agentic loop ──
    if not llm_client:
        return _error("LLM not available. Use /command or //command syntax.")

    return await _unified_loop(
        user_input=user_input,
        registry=registry,
        llm_client=llm_client,
        history=history,
        max_turns=max_turns,
        pipe_min_length=pipe_min_length,
        on_progress=on_progress,
    )


# ── Unified Loop ──


async def _unified_loop(
    user_input: str,
    registry: ToolRegistry,
    llm_client: LLMClient,
    history: list[dict] | None = None,
    max_turns: int = 5,
    pipe_min_length: int = 200,
    on_progress: Callable[[dict], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    """Unified agentic loop — LLM converses and chains tools as needed.

    Single loop handles everything: simple queries, multi-step chains,
    and pure conversation. Large data (sequences, etc.) is cached locally
    and auto-injected into subsequent tools — never sent through LLM context.
    """
    tools = registry.llm_tools()
    schemas = build_multi_tool_schema(tools)
    tool_map = {t.name: t for t in tools}

    messages = [{"role": "system", "content": build_system_prompt(registry)}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_input})

    last_result = None
    last_tool = None
    last_params = {}
    chain = []  # [{tool, params, summary, widget}]
    cache = {}  # hybrid auto-pipe: field_name → large string value
    tokens = {"in": 0, "out": 0}
    exceeded = False

    async def _emit(phase: str, tool: str | None = None):
        if on_progress:
            data: dict[str, Any] = {"phase": phase, "tools_used": len(chain), "tokens": tokens}
            if tool:
                data["tool"] = tool
            await on_progress(data)

    await _emit("thinking")

    for turn in range(max_turns):
        try:
            response = await llm_client.chat(messages, tools=schemas)
        except Exception as e:
            logger.error("Unified loop LLM call failed (turn %d): %s", turn, e)
            exceeded = True
            break

        # Accumulate token usage
        usage = response.get("usage") or {}
        tokens["in"] += usage.get("prompt_tokens", 0)
        tokens["out"] += usage.get("completion_tokens", 0)

        msg = response["choices"][0]["message"]

        # LLM responded with text — done
        if not msg.get("tool_calls"):
            content = msg.get("content", "")
            logger.info(
                "Unified loop done after %d turn(s): %s",
                turn + 1, [s["tool"] for s in chain],
            )

            if last_result and last_tool:
                resp = _tool_response(last_tool, last_result, last_params, content)
                if chain:
                    resp["chain"] = chain
                return resp

            return {"type": "message", "content": content}

        # Append assistant message with tool_calls
        messages.append(msg)

        for tc in msg["tool_calls"]:
            tool_name = tc["function"]["name"]
            tool = tool_map.get(tool_name)

            try:
                params = json.loads(tc["function"]["arguments"]) if isinstance(
                    tc["function"]["arguments"], str
                ) else tc["function"]["arguments"]
                params = {k: v for k, v in params.items() if v is not None}
            except (json.JSONDecodeError, AttributeError):
                params = {}

            if not tool:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": f"Error: unknown tool '{tool_name}'",
                })
                continue

            # Hybrid auto-pipe: inject cached values into matching params
            # Override if param is missing, empty, or shorter than the cached
            # value (LLM sometimes puts placeholder text like "injected")
            schema_props = tool.input_schema().get("properties", {})
            for key in schema_props:
                if key not in cache:
                    continue
                provided = params.get(key)
                if not provided or (
                    isinstance(provided, str) and len(provided) < pipe_min_length
                ):
                    params[key] = cache[key]
                    logger.info("Cache inject: %s (%d chars)", key, len(str(cache[key])))

            await _emit("tool", tool_name)
            try:
                result = await tool.execute(params)
            except Exception as e:
                logger.error("Tool %s failed: %s", tool_name, e)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": f"Error: {e}",
                })
                await _emit("thinking")
                continue

            # Hybrid auto-pipe: stash large string values for subsequent tools
            for key, val in result.items():
                if isinstance(val, str) and len(val) >= pipe_min_length:
                    cache[key] = val

            compact = tool.summary_for_llm(result)
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": compact,
            })

            chain.append({
                "tool": tool_name,
                "params": params,
                "summary": tool.format_result(result),
                "widget": tool.widget,
            })
            logger.info("Unified turn %d: %s(%s)", turn + 1, tool_name, json.dumps(params))

            last_result = result
            last_tool = tool_name
            last_params = params
            await _emit("thinking")
    else:
        # for-loop exhausted without break → max turns exceeded
        exceeded = True
        logger.warning(
            "Unified loop hit max turns (%d): %s",
            max_turns, [s["tool"] for s in chain],
        )

    if not chain:
        return _error("No tools were called during reasoning.")

    # Max turns exceeded — use last step's summary as fallback
    fallback = chain[-1]["summary"] if chain else ""
    if exceeded:
        fallback += " (reached maximum reasoning steps)"

    if last_result and last_tool:
        resp = _tool_response(last_tool, last_result, last_params, fallback)
        resp["chain"] = chain
        return resp

    return {"type": "message", "content": fallback, "chain": chain}


# ── Helpers ──


def _parse_args(text: str) -> dict:
    """Try to parse text as JSON params, fall back to {'query': text}."""
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"query": text}


def _tool_response(tool_name: str, result: dict, params: dict, content: str) -> dict:
    return {
        "type": "tool_result",
        "tool": tool_name,
        "data": result,
        "params": params,
        "content": content,
    }


def _form_response(tool_name: str, description: str, schema: dict) -> dict:
    return {
        "type": "form",
        "tool": tool_name,
        "data": {"schema": schema, "tool_name": tool_name, "description": description},
        "content": f"Fill in the required parameters for **{tool_name}**:",
    }


def _help_response(registry: ToolRegistry) -> dict:
    """Build a help message listing all available commands."""
    lines = ["**Available commands:**\n"]
    for tool in registry.visible_tools():
        tag = "" if "llm" in tool.tags else " *(direct only)*"
        lines.append(f"- **/{tool.name}**{tag} — {tool.description}")
    lines.append("\nPrefix with `//` for direct execution (no LLM), e.g. `//search ampicillin`.")
    return {"type": "message", "content": "\n".join(lines)}


def _error(msg: str) -> dict:
    return {"type": "message", "content": msg}
