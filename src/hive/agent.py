"""Tool router -- dispatches user input to the correct tool via LLM or direct invocation."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from hive.context import current_chat_tasks
from hive.llm import LLMClient, build_system_prompt
from hive.sandbox import SandboxRunner, Workspace
from hive.tools import ToolRegistry

if TYPE_CHECKING:
    from hive.llm import Planner

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
    Route user input -> tool execution -> response.

    Three modes:
      //command args -> direct tool execution, no LLM
      /command args  -> LLM extracts params for specified tool, then summarizes
      free text      -> unified agentic loop (LLM picks tools, chains, converses)
    """

    # -- /help or //help -- list available commands --
    if user_input.strip().lstrip("/") == "help":
        return _help_response(registry)

    # -- Mode 1: Direct -- //command --
    if match := DIRECT_PATTERN.match(user_input):
        tool_name = match.group(1)
        args_text = match.group(2).strip()
        tool = registry.get(tool_name)
        if not tool:
            return _error(f"Unknown tool: {tool_name}")

        # No args -> always show form (all visible tools must have one)
        if not args_text:
            return _form_response(tool_name, tool.long_desc, tool.input_schema())

        params = _parse_args(args_text)
        result = await tool.execute(params)
        return _tool_response(tool_name, result, params, tool.format_result(result))

    # -- Mode 2: Guided -- /command --
    if match := GUIDED_PATTERN.match(user_input):
        tool_name = match.group(1)
        text = match.group(2).strip()
        tool = registry.get(tool_name)
        if not tool:
            return _error(f"Unknown tool: {tool_name}")

        if not llm_client:
            # No LLM -- execute directly
            if not text:
                return _form_response(tool_name, tool.long_desc, tool.input_schema())

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

    # -- Mode 3: Natural language -- unified agentic loop --
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


# -- Unified Loop --


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
    """Unified agentic loop -- LLM converses and chains tools as needed.

    Flat context: messages are rebuilt from scratch each turn. A compact
    turn_log replaces accumulated assistant+tool message pairs.

    LLM sees exactly 2 tools: tasks (function-calling) + python (sandbox).
    All other tools (search, blast, profile, ...) are callable from python code.
    """

    # Build tasks schema once -- only tasks gets a function-calling schema
    tasks = registry.get("tasks")
    assert tasks, "tasks tool must be registered"
    tasks_schema = {
        "type": "function",
        "function": {
            "name": "tasks",
            "description": tasks.short_desc,
            "parameters": tasks.llm_schema(),
        },
    }

    last_result = None
    last_tool = None
    last_params = {}
    last_feedback = ""  # last successful sandbox feedback (for widget header)
    chain = []  # [{tool, params, summary}]
    if workspace is None:
        workspace = Workspace()
    workspace.reset_loop()
    sandbox = SandboxRunner(
        workspace,
        output_limit=sandbox_output_limit,
        registry=registry,
        tool_call_budget=tool_call_budget,
    )
    tokens = {"in": 0, "out": 0}
    error_msg = ""  # LLM error message (vs max_turns exhaustion)
    plan_text = None  # plan injected into agent context

    async def _emit(phase: str, tool: str | None = None):
        if on_progress:
            data: dict[str, Any] = {"phase": phase, "tools_used": len(chain), "tokens": tokens}
            if tool:
                data["tool"] = tool
            await on_progress(data)

    await _emit("thinking")

    # -- Optional planner (produces task description for agent context) --
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

    def _build_messages() -> list[dict]:
        """Rebuild messages from scratch each turn -- flat context."""
        msgs: list[dict] = [{"role": "system", "content": build_system_prompt()}]

        if task_ctx:
            msgs.append({"role": "system", "content": task_ctx})

        # Workspace context from previous messages (r<N> handles only on first turn)
        ws_ctx = ""
        if len(workspace) > 0 and not workspace.steps:
            ws_ctx = f"\n\n[Workspace]\n{workspace.describe()}"

        if plan_text:
            msgs.append(
                {
                    "role": "user",
                    "content": f"[Plan]\n{plan_text}\n\n[User request]\n{user_input}{ws_ctx}",
                }
            )
        else:
            if history:
                msgs.extend(history)
            msgs.append({"role": "user", "content": f"{user_input}{ws_ctx}"})

        progress = workspace.history()
        if progress:
            msgs.append({"role": "assistant", "content": f"Done so far:\n{progress}"})
            msgs.append({"role": "user", "content": "Continue."})

        return msgs

    for turn in range(max_turns):
        # Rebuild messages from scratch -- no accumulated pairs
        messages = _build_messages()

        # tasks + python always available
        turn_tools = [tasks_schema, sandbox.tool_schema()]

        # Log payload sizes for token debugging
        msg_chars = sum(len(str(m.get("content", ""))) for m in messages)
        schema_chars = sum(len(json.dumps(s)) for s in turn_tools) if turn_tools else 0
        logger.info(
            "CONTEXT turn %d: %d msgs (%d chars) + schemas (%d chars) = %d chars",
            turn,
            len(messages),
            msg_chars,
            schema_chars,
            msg_chars + schema_chars,
        )
        try:
            response = await llm_client.chat(messages, tools=turn_tools)
        except Exception as e:
            sanitized = _sanitize_llm_error(str(e))
            # Rate limit: wait and retry once (on top of litellm's own retries)
            if sanitized == "Rate limit reached":
                logger.warning("Rate limit hit (turn %d), retrying in 15s", turn)
                await asyncio.sleep(15)
                try:
                    response = await llm_client.chat(messages, tools=turn_tools)
                except Exception as e2:
                    logger.error("LLM retry failed (turn %d): %s", turn, e2)
                    error_msg = _sanitize_llm_error(str(e2))
                    break
            else:
                logger.error("LLM call failed (turn %d): %s", turn, e)
                error_msg = sanitized
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

        # LLM responded with text -- done
        if not msg.get("tool_calls"):
            content = msg.get("content", "")
            logger.info(
                "Unified loop done after %d turn(s): %s",
                turn + 1,
                [s["tool"] for s in chain],
            )

            # Successful completion -- flush report to r<N> handles
            if sandbox.report:
                sandbox.flush_report()
                last_result = sandbox.report
                last_tool = "python"
                last_params = {"feedback": last_feedback} if last_feedback else {}

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

                compact = sandbox.summary_for_llm(sb_result)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": compact,
                    }
                )

                # Record step + chain
                if sb_result["status"] != "ok":
                    err_text = sb_result.get("error", "unknown")
                    hint = _error_hint(err_text, workspace, sandbox)
                    workspace.add_step(
                        "python", err_text, code=code, error=err_text, hint=hint,
                    )
                    display_summary = f"Error: {err_text}"
                else:
                    fb = str(sb_result.get("feedback", ""))[:100]
                    last_feedback = fb
                    produced = _build_produced(workspace, sandbox)
                    workspace.add_step("python", fb, code=code, produced=produced)
                    display_summary = fb

                chain.append(
                    {
                        "tool": "python",
                        "params": {"code": code},
                        "summary": display_summary,
                    }
                )

                logger.info("Sandbox exec: %s", compact[:200])
                await _emit("thinking")
                continue

            # Only tasks is exposed as a function-calling tool.
            # All other tools are callable from python -- reject hallucinated direct calls.
            if tool_name != "tasks":
                err = f"'{tool_name}' is callable from python: {tool_name}(param=value)"
                messages.append(
                    {"role": "tool", "tool_call_id": tc["id"], "content": err}
                )
                workspace.add_step(tool_name, err, error=err)
                continue

            result = await tasks.execute(params)
            compact = tasks.format_result(result)
            messages.append(
                {"role": "tool", "tool_call_id": tc["id"], "content": compact}
            )
            workspace.add_step("tasks", compact)
            chain.append({"tool": "tasks", "params": params, "summary": compact})
            logger.info("Unified turn %d: tasks(%s)", turn + 1, json.dumps(params))
            await _emit("thinking")

    else:
        # for-loop exhausted without break -> max turns exceeded
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
        if error_msg:
            resp["llm_error"] = True
        if plan_text:
            resp["plan"] = plan_text
        return resp

    # -- Final summary round: ask LLM to review results (no tools) --
    fallback = ""
    if chain and not error_msg:
        fallback = await _final_summary(
            user_input, workspace, sandbox, llm_client, tokens,
        )

    if not fallback:
        if error_msg:
            fallback = f"Analysis stopped due to an error: {error_msg}"
        elif last_feedback:
            fallback = last_feedback
        else:
            fallback = chain[-1]["summary"] if chain else ""

    # Flush report only when no LLM error -- preserve workspace for retry
    if sandbox.report:
        if not error_msg:
            sandbox.flush_report()
        last_result = sandbox.report
        last_tool = "python"
        last_params = {"feedback": last_feedback} if last_feedback else {}

    if last_result and last_tool:
        resp = _tool_response(last_tool, last_result, last_params, fallback)
        resp["tokens"] = tokens
        resp["chain"] = chain
        if sandbox.report:
            resp["report"] = True
        if error_msg:
            resp["llm_error"] = True
        if plan_text:
            resp["plan"] = plan_text
        return resp

    resp = {"type": "message", "content": fallback, "tokens": tokens, "chain": chain}
    if error_msg:
        resp["llm_error"] = True
    if plan_text:
        resp["plan"] = plan_text
    return resp


# -- Final Summary --


async def _final_summary(
    user_input: str,
    workspace: Workspace,
    sandbox: SandboxRunner,
    llm_client: LLMClient,
    tokens: dict[str, int],
) -> str:
    """One last LLM call (no tools) to produce a user-facing summary.

    Called when the agentic loop finishes without a natural text response
    (max turns exceeded or break without content).
    """
    report_keys = list(sandbox.report.keys()) if sandbox.report else []
    steps = workspace.history()

    prompt = (
        f"The user asked: {user_input}\n\n"
        f"You completed these steps:\n{steps}\n\n"
    )
    if report_keys:
        prompt += f"Report sections ready: {', '.join(report_keys)}\n\n"
    prompt += (
        "Write a 1-3 sentence summary of what you found for the user. "
        "Do NOT repeat table data -- the user can see it in the widget. "
        "Be concise and direct."
    )

    try:
        response = await llm_client.chat(
            [
                {"role": "system", "content": build_system_prompt()},
                {"role": "user", "content": prompt},
            ],
            tools=None,
        )
        usage = response.get("usage") or {}
        tokens["in"] += usage.get("prompt_tokens", 0)
        tokens["out"] += usage.get("completion_tokens", 0)
        return response["choices"][0]["message"].get("content", "")
    except Exception as e:
        logger.warning("Final summary call failed: %s", e)
        return ""


# -- Helpers --


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
        lines.append(f"- **/{tool.name}** -- {tool.long_desc}")
    lines.append("\nPrefix with `//` for direct execution (no LLM), e.g. `//search ampicillin`.")
    return {"type": "message", "content": "\n".join(lines)}


def _error(msg: str) -> dict:
    return {"type": "message", "content": msg}


def _error_hint(err_text: str, workspace: Workspace, sandbox: SandboxRunner) -> str | None:
    """Build actionable hint for common sandbox errors."""
    import re as _re

    # KeyError 'foo' -> show available keys
    m = _re.search(r"KeyError:?\s*['\"](\w+)['\"]", err_text)
    if m:
        # Try to find a list[dict] in workspace to show its keys
        for e in reversed(workspace._entries):
            if isinstance(e.value, list) and e.value and isinstance(e.value[0], dict):
                keys = ", ".join(list(e.value[0].keys())[:8])
                return f"keys: {{{keys}}}"
        return None

    # NameError 'bar' -> show available names
    m = _re.search(r"NameError:?\s*.*?'(\w+)'", err_text)
    if m:
        ns = list(workspace.namespace().keys())
        uv = list(workspace.user_vars.keys())
        available = ns + uv + list(sandbox.report.keys())
        if available:
            return f"available: {', '.join(available[:10])}"
    return None


def _build_produced(workspace: Workspace, sandbox: SandboxRunner) -> str | None:
    """Summarize what a successful sandbox call produced."""
    parts: list[str] = []

    # New report keys
    if sandbox.report:
        rkeys = list(sandbox.report.keys())
        if rkeys:
            parts.append(f"report[{', '.join(repr(k) for k in rkeys[-2:])}]")

    # Count user vars
    uv = workspace.user_vars
    if uv:
        names = list(uv.keys())[-3:]
        parts.append(", ".join(names))

    return ", ".join(parts) if parts else None
