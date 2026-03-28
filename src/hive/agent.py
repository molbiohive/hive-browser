"""Agent -- dispatches user input to the correct tool via LLM or direct invocation."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from hive.llm import LLMClient
from hive.llm.worker import Worker
from hive.sandbox import Workspace
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
    """Route user input -> tool execution -> response.

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
        return await _run_agents(
            user_input=prompt,
            registry=registry,
            llm_client=llm_client,
            history=history,
            max_turns=max_turns,
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

    return await _run_agents(
        user_input=user_input,
        registry=registry,
        llm_client=llm_client,
        history=history,
        max_turns=max_turns,
        sandbox_output_limit=sandbox_output_limit,
        on_progress=on_progress,
        planner=planner,
        use_planner=use_planner,
        workspace=workspace,
        tool_call_budget=tool_call_budget,
    )


# -- Agent orchestration --


async def _run_agents(
    user_input: str,
    registry: ToolRegistry,
    llm_client: LLMClient,
    history: list[dict] | None = None,
    max_turns: int = 5,
    sandbox_output_limit: int = 4000,
    on_progress: Callable[[dict], Awaitable[None]] | None = None,
    planner: Planner | None = None,
    use_planner: bool = True,
    workspace: Workspace | None = None,
    tool_call_budget: int = 100,
) -> dict[str, Any]:
    """Run planner (optional) -> worker agentic loop."""
    if workspace is None:
        workspace = Workspace()

    # -- Optional planner --
    plan_text = None
    plan_tokens: dict[str, int] = {"in": 0, "out": 0}
    if planner and use_planner:
        try:
            plan_text, plan_tokens = await planner.prepare(
                user_input, history,
            ).run(llm_client)
        except Exception as e:
            logger.warning("Planner failed, continuing without plan: %s", e)

    # -- Worker --
    worker = Worker(
        registry, workspace,
        output_limit=sandbox_output_limit,
        tool_call_budget=tool_call_budget,
    )
    worker.prepare(
        user_input,
        plan=plan_text,
        history=history,
        on_progress=on_progress,
    )
    result = await worker.run(llm_client, max_turns=max_turns)

    # Merge planner tokens into result
    if plan_tokens.get("in") or plan_tokens.get("out"):
        result.setdefault("tokens", {"in": 0, "out": 0})
        result["tokens"]["in"] += plan_tokens.get("in", 0)
        result["tokens"]["out"] += plan_tokens.get("out", 0)

    return result


# -- Helpers --


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
    lines = ["**Available commands:**\n"]
    for tool in registry.tools():
        lines.append(f"- **/{tool.name}** -- {tool.long_desc}")
    lines.append("\nPrefix with `//` for direct execution (no LLM), e.g. `//search ampicillin`.")
    return {"type": "message", "content": "\n".join(lines)}


def _error(msg: str) -> dict:
    return {"type": "message", "content": msg}
