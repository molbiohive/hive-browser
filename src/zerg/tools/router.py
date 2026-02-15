"""Tool router — dispatches user input to the correct tool via LLM or direct invocation."""

import logging
import re

from zerg.tools.base import ToolRegistry

logger = logging.getLogger(__name__)

# Pattern: //command (direct tool, no LLM)
DIRECT_PATTERN = re.compile(r"^//(\w+)\s*(.*)", re.DOTALL)

# Pattern: /command (guided, LLM-assisted)
GUIDED_PATTERN = re.compile(r"^/(\w+)\s*(.*)", re.DOTALL)


async def route_input(user_input: str, registry: ToolRegistry, llm_client=None) -> dict:
    """
    Route user input to the appropriate tool.

    Three modes:
      - //command  → direct tool execution (no LLM), returns form schema or executes
      - /command   → LLM uses the specified tool first, can chain
      - free text  → LLM selects tool(s) autonomously
    """
    # Mode 3: Direct tool — //command
    if match := DIRECT_PATTERN.match(user_input):
        tool_name = match.group(1)
        tool = registry.get(tool_name)
        if not tool:
            return {"error": f"Unknown tool: {tool_name}"}

        return {
            "mode": "direct",
            "tool": tool_name,
            "schema": tool.schema(),
        }

    # Mode 2: Guided command — /command
    if match := GUIDED_PATTERN.match(user_input):
        tool_name = match.group(1)
        text = match.group(2).strip()
        tool = registry.get(tool_name)
        if not tool:
            return {"error": f"Unknown tool: {tool_name}"}

        # TODO: pass to LLM with hint to use this tool first
        return {
            "mode": "guided",
            "tool": tool_name,
            "text": text,
        }

    # Mode 1: Natural language — LLM selects tool
    # TODO: send to LLM with tool schemas for function calling
    return {
        "mode": "natural",
        "text": user_input,
    }
