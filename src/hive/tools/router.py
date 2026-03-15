"""Tool router — dispatches user input to the correct tool via LLM or direct invocation."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from hive.llm.client import LLMClient
from hive.llm.prompts import (
    build_tool_schema,
    build_system_prompt,
)
from hive.sandbox import SandboxRunner, Workspace
from hive.tools.base import ToolRegistry

if TYPE_CHECKING:
    from hive.llm.tool_rag import ToolRAG

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
    sandbox_output_limit: int = 4000,
    python_max_turns: int = 6,
    on_progress: Callable[[dict], Awaitable[None]] | None = None,
    tool_rag: ToolRAG | None = None,
    use_planner: bool = True,
    sandbox_max_retries: int = 3,
    context_char_limit: int = 0,
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

        # No args → always show form (all visible tools must have one)
        if not args_text:
            return _form_response(tool_name, tool.description, tool.input_schema())

        params = _parse_args(args_text)
        result = await tool.execute(params, mode="direct")
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
                return _form_response(tool_name, tool.description, tool.input_schema())

            params = _parse_args(text)
            result = await tool.execute(params, mode="guided")
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
            sandbox_output_limit=sandbox_output_limit,
            python_max_turns=python_max_turns,
            on_progress=on_progress,
            tool_rag=tool_rag,
            use_planner=use_planner,
            sandbox_max_retries=sandbox_max_retries,
            context_char_limit=context_char_limit,
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
        sandbox_output_limit=sandbox_output_limit,
        python_max_turns=python_max_turns,
        on_progress=on_progress,
        tool_rag=tool_rag,
        use_planner=use_planner,
        sandbox_max_retries=sandbox_max_retries,
        context_char_limit=context_char_limit,
    )


# ── Unified Loop ──


async def _unified_loop(
    user_input: str,
    registry: ToolRegistry,
    llm_client: LLMClient,
    history: list[dict] | None = None,
    max_turns: int = 5,
    pipe_min_length: int = 200,
    sandbox_output_limit: int = 4000,
    python_max_turns: int = 6,
    on_progress: Callable[[dict], Awaitable[None]] | None = None,
    tool_rag: ToolRAG | None = None,
    use_planner: bool = True,
    sandbox_max_retries: int = 3,
    context_char_limit: int = 0,
) -> dict[str, Any]:
    """Unified agentic loop — LLM converses and chains tools as needed.

    Single loop handles everything: simple queries, multi-step chains,
    and pure conversation. ALL tool results go to workspace — LLM sees
    descriptors and queries data via python sandbox.

    Two-mode RAG pipeline (when tool_rag is provided):
    - Planner ON:  planning call → RAG on plan → agent sees plan + selected tools
    - Planner OFF: RAG on user input directly → agent sees user input + selected tools
    Without tool_rag, all tools are used (backward compatible).
    """

    all_tools = registry.llm_tools()
    tool_map = {t.name: t for t in all_tools}
    all_schemas = build_tool_schema(all_tools)

    last_result = None
    last_tool = None
    last_params = {}
    chain = []  # [{tool, params, summary, widget}]
    workspace = Workspace()
    sandbox = SandboxRunner(workspace, output_limit=sandbox_output_limit)
    tokens = {"in": 0, "out": 0}
    exceeded = False
    error_msg = ""  # LLM error message (vs max_turns exhaustion)
    schemas = all_schemas
    plan_text = None  # plan injected into agent context
    sandbox_errors = 0  # consecutive sandbox errors (for retry limit)
    python_turns = 0  # separate python turn counter

    async def _emit(phase: str, tool: str | None = None):
        if on_progress:
            data: dict[str, Any] = {"phase": phase, "tools_used": len(chain), "tokens": tokens}
            if tool:
                data["tool"] = tool
            await on_progress(data)

    await _emit("thinking")

    # ── Tool Selection (RAG + optional planner) ──
    if tool_rag:
        try:
            if use_planner:
                # Mode 1: Planner ON — planning call decides intent, plan guides RAG + agent
                prefix, plan_content, plan_usage = await tool_rag.plan(
                    user_input, llm_client, history,
                )
                tokens["in"] += plan_usage.get("in", 0)
                tokens["out"] += plan_usage.get("out", 0)

                if prefix == "ANSWER":
                    return {"type": "message", "content": plan_content, "tokens": tokens}

                # RAG on plan content (planner's description of steps)
                selected = await tool_rag.select(plan_content)
                plan_text = plan_content
            else:
                # Mode 2: No planner — RAG on raw user input
                selected = await tool_rag.select(user_input)

            tool_map = {t.name: t for t in selected}
            schemas = build_tool_schema(selected)
            logger.info(
                "RAG selected %d tools: %s",
                len(selected), sorted(t.name for t in selected),
            )
        except Exception as e:
            logger.warning("Tool selection failed, using all tools: %s", e)

    # Build message list — plan augments user input (both visible to agent)
    messages = [{"role": "system", "content": build_system_prompt()}]
    if history:
        messages.extend(history)
    if plan_text:
        messages.append({"role": "user", "content": (
            f"[Plan]\n{plan_text}\n\n[User request]\n{user_input}"
        )})
    else:
        messages.append({"role": "user", "content": user_input})

    for turn in range(max_turns):
        turn_tools = schemas
        # Inject python schema when cached data is available (skip after too many errors)
        if (
            len(workspace) > 0
            and sandbox_errors < sandbox_max_retries
            and python_turns < python_max_turns
        ):
            turn_tools = [*schemas, sandbox.tool_schema()]

        # Log payload sizes for token debugging
        msg_chars = sum(len(str(m.get("content", ""))) for m in messages)
        schema_chars = sum(
            len(json.dumps(s)) for s in turn_tools
        ) if turn_tools else 0
        logger.debug(
            "PAYLOAD turn %d: %d msgs (%d chars) + %d tool schemas (%d chars)",
            turn, len(messages), msg_chars, len(turn_tools) if turn_tools else 0, schema_chars,
        )
        if context_char_limit > 0:
            _trim_context(messages, context_char_limit)

        try:
            response = await llm_client.chat(messages, tools=turn_tools)
        except Exception as e:
            logger.error("LLM call failed (turn %d): %s", turn, e)
            error_msg = str(e)
            exceeded = True
            break

        # Accumulate token usage
        usage = response.get("usage") or {}
        turn_in = usage.get("prompt_tokens", 0)
        turn_out = usage.get("completion_tokens", 0)
        tokens["in"] += turn_in
        tokens["out"] += turn_out
        logger.debug(
            "TOKENS turn %d: in=%d out=%d (cum: in=%d out=%d) | msgs=%d tools=%d",
            turn, turn_in, turn_out, tokens["in"], tokens["out"],
            len(messages), len(turn_tools) if turn_tools else 0,
        )

        msg = response["choices"][0]["message"]
        finish = response["choices"][0].get("finish_reason", "")

        # Handle model refusal gracefully
        if finish == "refusal":
            content = msg.get("content", "")
            return {
                "type": "message",
                "content": content or "Request declined by the model.",
                "tokens": tokens,
            }

        # LLM responded with text — done
        if not msg.get("tool_calls"):
            content = msg.get("content", "")
            logger.info(
                "Unified loop done after %d turn(s): %s",
                turn + 1, [s["tool"] for s in chain],
            )

            # Report dict populated by sandbox → becomes the widget data
            if sandbox.report:
                last_result = sandbox.report
                last_tool = "python"
                last_params = {}

            if last_result and last_tool:
                resp = _tool_response(last_tool, last_result, last_params, content)
                resp["tokens"] = tokens
                if chain:
                    resp["chain"] = chain
                return resp

            resp = {"type": "message", "content": content, "tokens": tokens}
            if chain:
                resp["chain"] = chain
            return resp

        # Append assistant message with tool_calls
        messages.append(msg)

        for tc in msg["tool_calls"]:
            tool_name = tc["function"]["name"]

            try:
                params = json.loads(tc["function"]["arguments"]) if isinstance(
                    tc["function"]["arguments"], str
                ) else tc["function"]["arguments"]
                params = {k: v for k, v in params.items() if v is not None}
            except (json.JSONDecodeError, AttributeError):
                params = {}

            args_raw = tc["function"].get("arguments", "{}")
            args_len = len(args_raw) if isinstance(args_raw, str) else len(json.dumps(args_raw))
            logger.debug(
                "TOOL_CALL %s: args=%d chars",
                tool_name, args_len,
            )

            # Built-in sandbox -- not a registered tool
            if tool_name == "python" and len(workspace) > 0:
                python_turns += 1
                code = params.get("code", "")
                sb_result = sandbox.execute(code)
                compact = sandbox.summary_for_llm(sb_result)
                ws_info = workspace.describe_all()
                if ws_info:
                    compact += f"\n\nWorkspace:\n{ws_info}"
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": compact,
                })

                # Human-readable chain summary (shown in UI, not sent to LLM)
                if sb_result["status"] != "ok":
                    chain_summary = f"Error: {sb_result.get('error', 'unknown')}"
                    sandbox_errors += 1
                else:
                    sandbox_errors = 0
                    desc = str(sb_result.get("feedback", ""))
                    chain_summary = desc[:80] if len(desc) > 80 else desc

                chain.append({
                    "tool": "python",
                    "params": {"code": code},
                    "summary": chain_summary,
                    "widget": "none",  # python never sets widget directly
                })

                logger.info("Sandbox exec: %s", compact[:200])
                await _emit("thinking")
                continue

            tool = tool_map.get(tool_name)

            if not tool:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": f"Error: unknown tool '{tool_name}'",
                })
                continue

            # Auto-fill from workspace: inject stored values into matching params
            # Override if param is missing, empty, or shorter than the stored value
            schema_props = tool.input_schema().get("properties", {})
            for key in schema_props:
                provided = params.get(key)
                if not provided or (
                    isinstance(provided, str) and len(provided) < pipe_min_length
                ):
                    cached = workspace.find_by_field(key, pipe_min_length)
                    if cached is not None:
                        params[key] = cached
                        logger.info("Workspace inject: %s (%d chars)", key, len(str(cached)))

            await _emit("tool", tool_name)
            result = await tool.execute(params, mode="natural")
            sandbox_errors = 0  # regular tool success resets sandbox error budget

            # Store full result in workspace (error results bypass)
            if "error" not in result:
                workspace.store_result(result, tool_name, params)
                compact = _build_tool_message(tool_name, result, workspace)
            else:
                compact = f"Error: {result['error']}"

            logger.debug(
                "TOOL_MSG %s: %d chars | result keys: %s",
                tool_name, len(compact),
                {k: type(v).__name__ + f"({len(v) if isinstance(v, (str, list)) else v})"
                 for k, v in result.items()},
            )
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
        if error_msg:
            return _error(f"LLM error: {error_msg}")
        return _error("No tools were called during reasoning.")

    # Max turns exceeded — use last step's summary as fallback
    fallback = chain[-1]["summary"] if chain else ""
    if exceeded:
        if error_msg:
            fallback += f" (LLM error: {error_msg})"
        else:
            fallback += " (reached maximum reasoning steps)"

    # Report dict populated by sandbox → becomes the widget data
    if sandbox.report:
        last_result = sandbox.report
        last_tool = "python"
        last_params = {}

    if last_result and last_tool:
        resp = _tool_response(last_tool, last_result, last_params, fallback)
        resp["tokens"] = tokens
        resp["chain"] = chain
        return resp

    return {"type": "message", "content": fallback, "tokens": tokens, "chain": chain}


# ── Context Trimmer ──


def _trim_context(messages: list[dict], limit: int) -> None:
    """Trim oldest tool-result messages when context exceeds char limit.

    Replaces content of the oldest ``role="tool"`` messages with ``[trimmed]``
    until total chars are within *limit*. Never trims the last tool message
    (the LLM needs it for the current turn). Modifies *messages* in-place.
    """
    total = sum(len(str(m.get("content", ""))) for m in messages)
    if total <= limit:
        return

    # Indices of tool messages, excluding the very last one
    tool_indices = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
    if len(tool_indices) > 1:
        tool_indices = tool_indices[:-1]  # protect the last tool msg
    else:
        return  # nothing safe to trim

    for idx in tool_indices:
        old_len = len(str(messages[idx].get("content", "")))
        messages[idx] = {**messages[idx], "content": "[trimmed]"}
        total -= old_len - len("[trimmed]")
        logger.warning("Context trimmed: msg %d (%d chars removed)", idx, old_len)
        if total <= limit:
            break


# ── Tool Message Builder ──


def _build_tool_message(tool_name: str, result: dict, workspace: Workspace) -> str:
    """Build concise tool message for LLM: confirmation + workspace descriptor.

    Scalar values are shown inline. Complex data (lists, dicts, strings) are
    available in workspace — LLM queries them via python sandbox.
    """
    parts = [f"{tool_name}: done."]
    ws_info = workspace.describe_all()
    if ws_info:
        parts.append(f"\nWorkspace:\n{ws_info}")
    return "\n".join(parts)


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
