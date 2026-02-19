"""Tool router — dispatches user input to the correct tool via LLM or direct invocation."""

import json
import logging
import re
from typing import Any

from zerg.llm.client import LLMClient
from zerg.llm.prompts import (
    build_agentic_prompt,
    build_chain_summary_prompt,
    build_execution_prompt,
    build_multi_tool_schema,
    build_selection_prompt,
    build_summary_prompt,
    build_tool_schema,
)
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
) -> dict[str, Any]:
    """
    Route user input → tool execution → response.

    Three modes:
      //command args → direct tool execution, no LLM
      /command args  → LLM extracts params for specified tool, then summarizes
      free text      → LLM picks mode (SIMPLE/LOOP) and tool(s)
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

        # LLM-assisted: skip selection (tool is known), go to execution + summary
        prompt = f"Use the {tool_name} tool: {text}" if text else f"Use the {tool_name} tool"
        return await _execute_and_summarize(
            tool=tool,
            user_input=prompt,
            llm_client=llm_client,
            history=history,
        )

    # ── Mode 3: Natural language — LLM picks mode + tools ──
    if not llm_client:
        return _error("LLM not available. Use /command or //command syntax.")

    return await _llm_tool_flow(
        user_input=user_input,
        registry=registry,
        llm_client=llm_client,
        history=history,
        max_turns=max_turns,
    )


# ── LLM Flow ──


async def _llm_tool_flow(
    user_input: str,
    registry: ToolRegistry,
    llm_client: LLMClient,
    history: list[dict] | None = None,
    max_turns: int = 5,
) -> dict[str, Any]:
    """LLM picks mode (SIMPLE/LOOP) and routes accordingly."""

    tool_names, mode = await _select_tools_and_mode(user_input, registry, llm_client, history)
    if not tool_names:
        return _error("I couldn't determine which tool to use. Try /command syntax.")

    if mode == "LOOP":
        return await _agentic_loop(
            user_input=user_input,
            registry=registry,
            llm_client=llm_client,
            max_turns=max_turns,
        )

    # SIMPLE mode — existing 3-step flow
    for tool_name in tool_names:
        tool = registry.get(tool_name)
        if not tool:
            logger.warning("LLM selected unknown tool: %s", tool_name)
            continue

        result = await _execute_and_summarize(
            tool=tool,
            user_input=user_input,
            llm_client=llm_client,
            history=history,
        )
        if result.get("type") != "message":
            return result

    return _error("No tools could process your request. Try rephrasing.")


async def _select_tools_and_mode(
    user_input: str,
    registry: ToolRegistry,
    llm_client: LLMClient,
    history: list[dict] | None = None,
) -> tuple[list[str], str]:
    """Step 1: LLM picks mode (SIMPLE/LOOP) and 1-3 tool names (~200 tokens)."""
    messages = [{"role": "system", "content": build_selection_prompt(registry)}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_input})

    try:
        response = await llm_client.chat(messages)
        content = response["choices"][0]["message"].get("content", "")
    except Exception as e:
        logger.error("Tool selection failed: %s", e)
        return [], "SIMPLE"

    # Parse mode
    mode = "SIMPLE"
    mode_match = re.search(r"MODE:\s*(SIMPLE|LOOP)", content, re.IGNORECASE)
    if mode_match:
        mode = mode_match.group(1).upper()

    # Parse tool names from response (one per line, after MODE line)
    known = {t.name for t in registry.llm_tools()}
    names = []
    for line in content.strip().split("\n"):
        line_clean = line.strip().lower().strip("-* ")
        # Skip the MODE line
        if line_clean.startswith("mode:"):
            continue
        if line_clean in known:
            names.append(line_clean)

    logger.info("Tool selection: %s → mode=%s tools=%s", user_input[:80], mode, names)
    return names, mode


async def _execute_and_summarize(
    tool,
    user_input: str,
    llm_client: LLMClient,
    history: list[dict] | None = None,
) -> dict[str, Any]:
    """Steps 2+3: Extract params via LLM, execute tool, then summarize."""

    # Step 2: Param extraction + execution
    schema = build_tool_schema(tool)
    messages = [{"role": "system", "content": build_execution_prompt(tool)}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_input})

    try:
        response = await llm_client.chat(messages, tools=schema)
    except Exception as e:
        logger.error("LLM execution call failed: %s", e)
        return _error(f"LLM unavailable: {e}")

    choice = response["choices"][0]
    msg = choice["message"]

    # If LLM didn't call the tool, return its text
    if not msg.get("tool_calls"):
        return {
            "type": "message",
            "content": msg.get("content", "I'm not sure how to help with that."),
        }

    tool_call = msg["tool_calls"][0]
    fn = tool_call["function"]

    try:
        params = (
            json.loads(fn["arguments"])
            if isinstance(fn["arguments"], str)
            else fn["arguments"]
        )
        params = {k: v for k, v in params.items() if v is not None}
        logger.info("LLM tool call: %s(%s)", tool.name, json.dumps(params))
        result = await tool.execute(params)
    except Exception as e:
        logger.error("Tool %s failed: %s", tool.name, e)
        return _error(f"Tool error: {e}")

    # Step 3: Summary from compact stats
    summary = await _summarize(tool, result, llm_client)

    return _tool_response(tool.name, result, params, summary)


async def _agentic_loop(
    user_input: str,
    registry: ToolRegistry,
    llm_client: LLMClient,
    max_turns: int = 5,
) -> dict[str, Any]:
    """Agentic loop — LLM chains tools until it has enough info to answer."""
    tools = registry.llm_tools()
    schemas = build_multi_tool_schema(tools)
    tool_map = {t.name: t for t in tools}

    messages = [
        {"role": "system", "content": build_agentic_prompt(registry)},
        {"role": "user", "content": user_input},
    ]

    last_result = None
    last_tool = None
    last_params = {}
    chain = []  # [{tool, params, summary, widget}]
    exceeded = False

    for turn in range(max_turns):
        try:
            response = await llm_client.chat(messages, tools=schemas)
        except Exception as e:
            logger.error("Agentic loop LLM call failed (turn %d): %s", turn, e)
            exceeded = True
            break

        msg = response["choices"][0]["message"]

        # LLM done — no more tool calls
        if not msg.get("tool_calls"):
            logger.info("Agentic loop done after %d turn(s): %s",
                        turn + 1, [s["tool"] for s in chain])
            break

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

            try:
                result = await tool.execute(params)
            except Exception as e:
                logger.error("Agentic tool %s failed: %s", tool_name, e)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": f"Error: {e}",
                })
                continue

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
            logger.info("Agentic turn %d: %s(%s)", turn + 1, tool_name, json.dumps(params))

            last_result = result
            last_tool = tool_name
            last_params = params
    else:
        # for-loop exhausted without break → max turns exceeded
        exceeded = True
        logger.warning("Agentic loop hit max turns (%d): %s",
                        max_turns, [s["tool"] for s in chain])

    if not chain:
        return _error("No tools were called during reasoning.")

    # Final summary — LLM summarizes the entire chain
    summary = await _summarize_chain(chain, llm_client, exceeded)

    if last_result and last_tool:
        resp = _tool_response(last_tool, last_result, last_params, summary)
        resp["chain"] = chain
        return resp

    return {"type": "message", "content": summary, "chain": chain}


async def _summarize_chain(
    chain: list[dict], llm_client: LLMClient, exceeded: bool = False,
) -> str:
    """Final step: LLM summarizes all chain results into a concise answer."""
    parts = []
    for i, step in enumerate(chain, 1):
        parts.append(f"Step {i} ({step['tool']}): {step['summary']}")
    chain_text = "\n".join(parts)

    messages = [
        {"role": "system", "content": build_chain_summary_prompt(chain_text, exceeded)},
        {"role": "user", "content": "Summarize."},
    ]

    try:
        response = await llm_client.chat(messages)
        return response["choices"][0]["message"].get("content", "")
    except Exception as e:
        logger.warning("Chain summary failed: %s", e)
        # Fallback: last step's summary
        return chain[-1]["summary"] if chain else ""


async def _summarize(tool, result: dict, llm_client: LLMClient) -> str:
    """Step 3: LLM writes summary from compact tool stats (~200 tokens)."""
    compact = tool.summary_for_llm(result)

    messages = [
        {"role": "system", "content": build_summary_prompt(compact)},
        {"role": "user", "content": "Summarize."},
    ]

    try:
        response = await llm_client.chat(messages)
        return response["choices"][0]["message"].get("content", "")
    except Exception as e:
        logger.warning("LLM summary failed: %s", e)
        return tool.format_result(result)


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
