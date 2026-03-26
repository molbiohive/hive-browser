"""Tool router — dispatches user input to the correct tool via LLM or direct invocation."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from hive.context import current_chat_tasks
from hive.llm.client import LLMClient
from hive.llm.prompts import build_system_prompt
from hive.sandbox import SandboxRunner, Workspace
from hive.tools.base import ToolRegistry

if TYPE_CHECKING:
    from hive.llm.planner import Planner

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
    on_progress: Callable[[dict], Awaitable[None]] | None = None,
    planner: Planner | None = None,
    use_planner: bool = True,
    workspace: Workspace | None = None,
    tool_call_budget: int = 100,
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
        result = await tool.execute(params)
        return _tool_response(tool_name, result, params, tool.format_result(result))

    # ── Mode 2: Guided — /command ──
    if match := GUIDED_PATTERN.match(user_input):
        tool_name = match.group(1)
        text = match.group(2).strip()
        tool = registry.get(tool_name)
        if not tool:
            return _error(f"Unknown tool: {tool_name}")

        if not llm_client:
            # No LLM — execute directly
            if not text:
                return _form_response(tool_name, tool.description, tool.input_schema())

            params = _parse_args(text)
            result = await tool.execute(params)
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
            on_progress=on_progress,
            planner=planner,
            use_planner=use_planner,
            workspace=workspace,
            tool_call_budget=tool_call_budget,
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
        on_progress=on_progress,
        planner=planner,
        use_planner=use_planner,
        workspace=workspace,
        tool_call_budget=tool_call_budget,
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
    on_progress: Callable[[dict], Awaitable[None]] | None = None,
    planner: Planner | None = None,
    use_planner: bool = True,
    workspace: Workspace | None = None,
    tool_call_budget: int = 100,
) -> dict[str, Any]:
    """Unified agentic loop — LLM converses and chains tools as needed.

    Flat context: messages are rebuilt from scratch each turn. A compact
    turn_log replaces accumulated assistant+tool message pairs.

    LLM sees exactly 2 tools: search (function-calling) + python (sandbox).
    All other tools are callable from python code.
    """

    # All tools available for direct execution and workspace auto-fill
    tool_map = {t.name: t for t in registry.tools()}

    # Build search schema once — only search gets a function-calling schema
    search = registry.get("search")
    assert search, "search tool must be registered"
    search_schema = {
        "type": "function",
        "function": {
            "name": "search",
            "description": search.guidelines or search.description,
            "parameters": search.llm_schema(),
        },
    }

    last_result = None
    last_tool = None
    last_params = {}
    chain = []  # [{tool, params, summary}]
    turn_log: list[tuple[str, str]] = []  # (tool_name, summary) — flat status
    if workspace is None:
        workspace = Workspace()
    sandbox = SandboxRunner(
        workspace,
        output_limit=sandbox_output_limit,
        registry=registry,
        tool_call_budget=tool_call_budget,
    )
    tokens = {"in": 0, "out": 0}
    exceeded = False
    error_msg = ""  # LLM error message (vs max_turns exhaustion)
    plan_text = None  # plan injected into agent context

    async def _emit(phase: str, tool: str | None = None):
        if on_progress:
            data: dict[str, Any] = {"phase": phase, "tools_used": len(chain), "tokens": tokens}
            if tool:
                data["tool"] = tool
            await on_progress(data)

    await _emit("thinking")

    # ── Optional planner (produces task description for agent context) ──
    if planner and use_planner:
        try:
            plan_content, plan_usage = await planner.plan(
                user_input,
                llm_client,
                history,
            )
            tokens["in"] += plan_usage.get("in", 0)
            tokens["out"] += plan_usage.get("out", 0)
            plan_text = plan_content
        except Exception as e:
            logger.warning("Planner failed, continuing without plan: %s", e)

    # Capture static context once (tasks, workspace history)
    task_ctx = ""
    chat_tasks = current_chat_tasks.get()
    if chat_tasks:
        task_lines = []
        for t in chat_tasks:
            mark = "x" if t.get("done") else " "
            task_lines.append(f"- [{mark}] {t.get('text', '')}")
        task_ctx = "Current tasks:\n" + "\n".join(task_lines)

    ws_history = ""
    if len(workspace) > 0:
        ws_history = f"\n\n[Workspace from previous messages]\n{workspace.describe_all()}"

    def _build_messages() -> list[dict]:
        """Rebuild messages from scratch each turn — flat context."""
        msgs: list[dict] = [{"role": "system", "content": build_system_prompt()}]

        if task_ctx:
            msgs.append({"role": "system", "content": task_ctx})

        if plan_text:
            msgs.append(
                {
                    "role": "user",
                    "content": f"[Plan]\n{plan_text}\n\n[User request]\n{user_input}{ws_history}",
                }
            )
        else:
            if history:
                msgs.extend(history)
            msgs.append({"role": "user", "content": f"{user_input}{ws_history}"})

        if turn_log:
            status = "\n".join(f"- {name}: {s}" for name, s in turn_log)
            msgs.append({"role": "assistant", "content": f"Done so far:\n{status}"})
            msgs.append({"role": "user", "content": "Continue."})

        return msgs

    for turn in range(max_turns):
        # Rebuild messages from scratch — no accumulated pairs
        messages = _build_messages()

        # search + python always available
        turn_tools = [search_schema, sandbox.tool_schema()]

        # Log payload sizes for token debugging
        msg_chars = sum(len(str(m.get("content", ""))) for m in messages)
        schema_chars = sum(len(json.dumps(s)) for s in turn_tools) if turn_tools else 0
        logger.debug(
            "PAYLOAD turn %d: %d msgs (%d chars) + %d tool schemas (%d chars)",
            turn,
            len(messages),
            msg_chars,
            len(turn_tools) if turn_tools else 0,
            schema_chars,
        )
        try:
            response = await llm_client.chat(messages, tools=turn_tools)
        except Exception as e:
            logger.error("LLM call failed (turn %d): %s", turn, e)
            error_msg = _sanitize_llm_error(str(e))
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
            turn,
            turn_in,
            turn_out,
            tokens["in"],
            tokens["out"],
            len(messages),
            len(turn_tools) if turn_tools else 0,
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
                turn + 1,
                [s["tool"] for s in chain],
            )

            # Report dict populated by sandbox → becomes the widget data
            if sandbox.report:
                last_result = sandbox.report
                last_tool = "python"
                last_params = {}

            if last_result and last_tool:
                resp = _tool_response(last_tool, last_result, last_params, content)
                resp["tokens"] = tokens
                if sandbox.report:
                    resp["report"] = True
                if chain:
                    resp["chain"] = chain
                if plan_text:
                    resp["plan"] = plan_text
                return resp

            resp = {"type": "message", "content": content, "tokens": tokens}
            if chain:
                resp["chain"] = chain
            if plan_text:
                resp["plan"] = plan_text
            return resp

        # Append assistant message with tool_calls for API compliance
        # (required: tool response must follow assistant with tool_calls)
        messages.append(msg)

        for tc in msg["tool_calls"]:
            tool_name = tc["function"]["name"]

            try:
                params = (
                    json.loads(tc["function"]["arguments"])
                    if isinstance(tc["function"]["arguments"], str)
                    else tc["function"]["arguments"]
                )
                params = {k: v for k, v in params.items() if v is not None}
            except (json.JSONDecodeError, AttributeError):
                params = {}

            args_raw = tc["function"].get("arguments", "{}")
            args_len = len(args_raw) if isinstance(args_raw, str) else len(json.dumps(args_raw))
            logger.debug(
                "TOOL_CALL %s: args=%d chars",
                tool_name,
                args_len,
            )

            # Built-in sandbox -- not a registered tool
            if tool_name == "python":
                code = params.get("code", "")
                sb_result = await sandbox.execute(code)

                # Auto-rerun: if NameError on an evicted handle, restore and retry once
                if sb_result["status"] == "error":
                    if await _try_restore_evicted(sb_result, workspace, registry):
                        sb_result = await sandbox.execute(code)

                compact = sandbox.summary_for_llm(sb_result)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": compact,
                    }
                )

                # Record in turn_log for flat context rebuild
                if sb_result["status"] != "ok":
                    chain_summary = f"Error: {sb_result.get('error', 'unknown')}"
                else:
                    desc = str(sb_result.get("feedback", ""))
                    chain_summary = desc[:100] if len(desc) > 100 else desc
                turn_log.append(("python", chain_summary))

                chain.append(
                    {
                        "tool": "python",
                        "params": {"code": code},
                        "summary": chain_summary,
                    }
                )

                logger.info("Sandbox exec: %s", compact[:200])
                await _emit("thinking")
                continue

            tool = tool_map.get(tool_name)

            if not tool:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": f"Error: unknown tool '{tool_name}'",
                    }
                )
                turn_log.append((tool_name, f"Error: unknown tool '{tool_name}'"))
                continue

            # Auto-fill from workspace: inject stored values into matching params
            # Override if param is missing, empty, or shorter than the stored value
            schema_props = tool.input_schema().get("properties", {})
            for key in schema_props:
                provided = params.get(key)
                if not provided or (isinstance(provided, str) and len(provided) < pipe_min_length):
                    cached = workspace.find_by_field(key, pipe_min_length)
                    if cached is not None:
                        params[key] = cached
                        logger.info("Workspace inject: %s (%d chars)", key, len(str(cached)))

            await _emit("tool", tool_name)

            result = await tool.execute(params)

            # Store full result in workspace (error results bypass)
            if "error" not in result:
                new_handles = workspace.store_result(result, tool_name, params)
                compact = _build_tool_message(tool_name, workspace, new_handles)
            else:
                compact = f"Error: {result['error']}"

            logger.debug(
                "TOOL_MSG %s: %d chars | result keys: %s",
                tool_name,
                len(compact),
                {
                    k: type(v).__name__ + f"({len(v) if isinstance(v, (str, list)) else v})"
                    for k, v in result.items()
                },
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": compact,
                }
            )

            # Record in turn_log for flat context rebuild
            summary = tool.format_result(result)
            turn_log.append((tool_name, summary))

            chain.append(
                {
                    "tool": tool_name,
                    "params": params,
                    "summary": summary,
                }
            )
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
            max_turns,
            [s["tool"] for s in chain],
        )

    if not chain:
        resp = (
            _error(f"LLM error: {error_msg}")
            if error_msg
            else _error("No tools were called during reasoning.")
        )
        if plan_text:
            resp["plan"] = plan_text
        return resp

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
        if sandbox.report:
            resp["report"] = True
        if plan_text:
            resp["plan"] = plan_text
        return resp

    resp = {"type": "message", "content": fallback, "tokens": tokens, "chain": chain}
    if plan_text:
        resp["plan"] = plan_text
    return resp


# ── Evicted Handle Auto-Rerun ──

_NAMEERROR_HANDLE_RE = re.compile(r"name '(r\d+)' is not defined")


async def _try_restore_evicted(
    sb_result: dict,
    workspace: Workspace,
    registry: ToolRegistry,
) -> bool:
    """If sandbox NameError references an evicted handle, re-run the tool and restore.

    Restores only the failed handle's tool call group. Returns True if sandbox
    should be retried. One retry per sandbox call — if the retry fails on a
    different evicted handle, the error goes back to the LLM.
    """
    error_str = sb_result.get("error", "")
    if "NameError" not in error_str:
        return False

    match = _NAMEERROR_HANDLE_RE.search(error_str)
    if not match:
        return False

    handle = match.group(1)
    idx = workspace._handle_index(handle)
    if idx is None:
        return False

    entry = workspace._entries[idx]
    if not entry.evicted:
        return False

    tool = registry.get(entry.tool)
    if not tool:
        return False

    try:
        result = await tool.execute(entry.params)
    except Exception as e:
        logger.warning("Auto-rerun %s failed: %s", entry.tool, e)
        return False

    # Restore all evicted entries from the same tool call
    for e in workspace._entries:
        if not e.evicted or e.tool != entry.tool or e.params != entry.params:
            continue
        if e.field_name == "_result":
            workspace.restore(e.handle, result)
        elif e.field_name in result:
            workspace.restore(e.handle, result[e.field_name])

    logger.info("Auto-restored evicted handle %s via %s rerun", handle, entry.tool)
    return True


# ── Tool Message Builder ──


def _build_tool_message(tool_name: str, workspace: Workspace, new_handles: list[str]) -> str:
    """Build concise tool message for LLM: confirmation + new handles only.

    Only shows handles created by this tool call to reduce token waste.
    Full workspace is visible via the python sandbox schema.
    """
    parts = [f"{tool_name}: done."]
    desc = workspace.describe_handles(new_handles)
    if desc:
        parts.append(f"\nStored:\n{desc}")
    return "\n".join(parts)


# ── Helpers ──


def _sanitize_llm_error(raw: str) -> str:
    """Turn raw LLM exceptions into short user-facing messages."""
    lowered = raw.lower()
    if "rate" in lowered and "limit" in lowered:
        return "Rate limit reached"
    if "auth" in lowered:
        return "LLM auth failed"
    if "timeout" in lowered:
        return "LLM request timed out"
    if "connect" in lowered:
        return "Could not connect to LLM"
    # Unknown: first sentence, capped
    first = raw.split(".")[0].split("\n")[0]
    return first[:120] if len(first) > 120 else first


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
    for tool in registry.tools():
        lines.append(f"- **/{tool.name}** — {tool.description}")
    lines.append("\nPrefix with `//` for direct execution (no LLM), e.g. `//search ampicillin`.")
    return {"type": "message", "content": "\n".join(lines)}


def _error(msg: str) -> dict:
    return {"type": "message", "content": msg}
