"""Tool router — dispatches user input to the correct tool via LLM or direct invocation."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from hive.llm.client import LLMClient
from hive.llm.prompts import (
    build_multi_tool_schema,
    build_system_prompt,
)
from hive.sandbox import ResultCache, SandboxRunner
from hive.secrets import SecretVault
from hive.tools.base import ToolRegistry

if TYPE_CHECKING:
    from hive.llm.tool_rag import ToolRAG

logger = logging.getLogger(__name__)

# Fields stripped from LLM summaries (large data, file paths, raw sequences)
_REDACT_KEYS = frozenset({
    "file_path", "path", "file_name", "filename",
    "sequence", "raw_sequence", "subject",
})

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
    summary_token_limit: int = 1000,
    on_progress: Callable[[dict], Awaitable[None]] | None = None,
    tool_rag: ToolRAG | None = None,
    use_planner: bool = True,
    sandbox_max_retries: int = 3,
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
            summary_token_limit=summary_token_limit,
            on_progress=on_progress,
            tool_rag=tool_rag,
            use_planner=use_planner,
            sandbox_max_retries=sandbox_max_retries,
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
        summary_token_limit=summary_token_limit,
        on_progress=on_progress,
        tool_rag=tool_rag,
        use_planner=use_planner,
        sandbox_max_retries=sandbox_max_retries,
    )


# ── Unified Loop ──


async def _unified_loop(
    user_input: str,
    registry: ToolRegistry,
    llm_client: LLMClient,
    history: list[dict] | None = None,
    max_turns: int = 5,
    pipe_min_length: int = 200,
    summary_token_limit: int = 1000,
    on_progress: Callable[[dict], Awaitable[None]] | None = None,
    tool_rag: ToolRAG | None = None,
    use_planner: bool = True,
    sandbox_max_retries: int = 3,
) -> dict[str, Any]:
    """Unified agentic loop — LLM converses and chains tools as needed.

    Single loop handles everything: simple queries, multi-step chains,
    and pure conversation. Large data (sequences, etc.) is cached locally
    and auto-injected into subsequent tools — never sent through LLM context.

    Two-mode RAG pipeline (when tool_rag is provided):
    - Planner ON:  planning call → RAG on plan → agent sees plan + selected tools
    - Planner OFF: RAG on user input directly → agent sees user input + selected tools
    Without tool_rag, all tools are used (backward compatible).
    """

    all_tools = registry.llm_tools()
    tool_map = {t.name: t for t in all_tools}
    all_schemas = build_multi_tool_schema(all_tools)

    last_result = None
    last_tool = None
    last_params = {}
    chain = []  # [{tool, params, summary, widget}]
    cache = {}  # hybrid auto-pipe: field_name → large string value (may be SEC: tokens)
    vault = SecretVault()  # per-loop vault for protecting sensitive data
    result_cache = ResultCache()  # per-loop cache for list[dict] results
    sandbox = SandboxRunner(result_cache)
    tokens = {"in": 0, "out": 0}
    exceeded = False
    schemas = all_schemas
    plan_text = None  # plan injected into agent context
    sandbox_errors = 0  # consecutive sandbox errors (for retry limit)

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
            schemas = build_multi_tool_schema(selected)
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
        if len(result_cache) > 0 and sandbox_errors < sandbox_max_retries:
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
        try:
            response = await llm_client.chat(messages, tools=turn_tools)
        except Exception as e:
            logger.error("Unified loop LLM call failed (turn %d): %s", turn, e)
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
            if tool_name == "python" and len(result_cache) > 0:
                code = params.get("code", "")
                sb_result = sandbox.execute(code)
                compact = sandbox.summary_for_llm(sb_result)
                cache_info = result_cache.describe_all()
                if cache_info:
                    compact += f"\n\nCached data:\n{cache_info}"
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": compact,
                })

                # Sandbox is the final computation — update last_result accordingly
                sb_val = sb_result.get("result")
                is_tabular = (
                    sb_result["status"] == "ok"
                    and isinstance(sb_val, list)
                    and sb_val
                    and isinstance(sb_val[0], dict)
                )

                # Human-readable chain summary (shown in UI, not sent to LLM)
                if sb_result["status"] != "ok":
                    chain_summary = f"Error: {sb_result.get('error', 'unknown')}"
                elif is_tabular:
                    chain_summary = f"Filtered to {len(sb_val)} row(s)"
                else:
                    short = str(sb_val)
                    chain_summary = f"Result: {short[:80]}" if len(short) > 80 else f"Result: {short}"

                chain.append({
                    "tool": "python",
                    "params": {"code": code},
                    "summary": chain_summary,
                    "widget": "table" if is_tabular else "none",
                })
                # Track consecutive sandbox errors for retry limit
                if sb_result["status"] != "ok":
                    sandbox_errors += 1
                else:
                    sandbox_errors = 0

                if is_tabular:
                    # List[dict] → show as table widget
                    last_result = {"results": sb_val}
                    last_tool = "python"
                    last_params = {"code": code}
                # Scalar → don't touch last_result/last_tool; previous tool's widget stays

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

            # Resolve SEC: tokens in params before execution
            params = vault.scan_and_resolve(params)

            await _emit("tool", tool_name)
            result = await tool.execute(params, mode="natural")
            sandbox_errors = 0  # regular tool success resets sandbox error budget

            # Hybrid auto-pipe: protect sensitive values, stash in cache
            protected = vault.scan_and_protect(result, min_length=pipe_min_length)
            for key, val in protected.items():
                if isinstance(val, str) and (
                    val.startswith("SEC:") or len(val) >= pipe_min_length
                ):
                    cache[key] = val

            # Auto-cache list[dict] fields for sandbox access
            for key, val in result.items():
                if (
                    isinstance(val, list)
                    and val
                    and isinstance(val[0], dict)
                ):
                    handle = result_cache.store(val, tool_name, params)
                    logger.info(
                        "Cached %s.%s as %s (%d rows)",
                        tool_name, key, handle, len(val),
                    )

            compact = _summarize_for_llm(result, token_limit=summary_token_limit)
            # Append cache descriptions so LLM knows what data is available
            cache_info = result_cache.describe_all()
            if cache_info:
                compact += f"\n\nCached data (use python tool to filter/transform):\n{cache_info}"
            logger.debug(
                "SUMMARY %s: %d chars | result keys: %s",
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
        return _error("No tools were called during reasoning.")

    # Max turns exceeded — use last step's summary as fallback
    fallback = chain[-1]["summary"] if chain else ""
    if exceeded:
        fallback += " (reached maximum reasoning steps)"

    if last_result and last_tool:
        resp = _tool_response(last_tool, last_result, last_params, fallback)
        resp["tokens"] = tokens
        resp["chain"] = chain
        return resp

    return {"type": "message", "content": fallback, "tokens": tokens, "chain": chain}


# ── Result Summarizer ──

_ID_KEYS = frozenset({"sid", "pid", "id"})


def _summarize_for_llm(
    result: dict[str, Any],
    token_limit: int = 1000,
) -> str:
    """Unified result summarizer for LLM context.

    Generates compact JSON stats from a result dict:
    - Lists → count + first N items as sample
    - Numbers/booleans → include directly
    - Short strings → include, long strings → truncate
    - Nested dicts → shallow scalar fields
    - Keys in _REDACT_KEYS stripped entirely

    For list[dict] fields with more items than the sample, ALL values
    of ID-like keys (sid, pid, id) are collected and appended as compact
    arrays so the LLM can reference them in subsequent tool calls.
    """
    redact = _REDACT_KEYS
    max_chars = token_limit * 4
    max_items = max(5, token_limit // 50)
    max_ids = 200
    stats: dict[str, Any] = {}

    for key, value in result.items():
        if key in redact:
            continue
        if isinstance(value, list):
            stats[f"{key}_count"] = len(value)
            if value and isinstance(value[0], dict):
                sample = []
                for item in value[:max_items]:
                    trimmed = {}
                    for k, v in item.items():
                        if k in redact:
                            continue
                        if isinstance(v, (str, int, float, bool, type(None))):
                            if not isinstance(v, str) or len(v) < 200:
                                trimmed[k] = v
                        elif isinstance(v, list) and len(v) <= 5 and all(
                            isinstance(x, (str, int, float)) for x in v
                        ):
                            trimmed[k] = v
                    sample.append(trimmed)
                if sample:
                    stats[f"{key}_sample"] = sample
                # Collect ALL IDs when sample is truncated
                if len(value) > max_items:
                    for id_key in _ID_KEYS:
                        ids = [item[id_key] for item in value[:max_ids] if id_key in item]
                        if ids:
                            stats[f"all_{key}_{id_key}s"] = ids
            elif value:
                stats[f"{key}_sample"] = value[:max_items]
        elif isinstance(value, (int, float, bool)):
            stats[key] = value
        elif isinstance(value, str):
            if len(value) < 200:
                stats[key] = value
            else:
                stats[key] = value[:100] + "..."
        elif isinstance(value, dict):
            shallow = {
                k: v for k, v in value.items()
                if k not in redact
                and isinstance(v, (str, int, float, bool, type(None)))
                and (not isinstance(v, str) or len(v) < 200)
            }
            if shallow:
                stats[key] = shallow

    text = json.dumps(stats, default=str)
    if len(text) > max_chars:
        text = text[:max_chars - 3] + "..."
    return text


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
