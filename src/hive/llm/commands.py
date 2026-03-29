"""LLM command schemas for the unified agent."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hive.tools.base import Tool

SEARCH_CMD: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "Search",
        "description": "List available skill procedures.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Optional keyword filter"},
            },
        },
    },
}

READ_CMD: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "Read",
        "description": "Read full content of a skill procedure.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Skill name"},
            },
            "required": ["name"],
        },
    },
}

PLAN_CMD: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "Plan",
        "description": "Switch to planner mode to research skills.",
        "parameters": {"type": "object", "properties": {}},
    },
}

PLANNER_CMDS: list[dict[str, Any]] = [SEARCH_CMD, READ_CMD]


def tasks_cmd(tasks_tool: Tool) -> dict[str, Any]:
    """Build Tasks command schema from the registered tasks tool."""
    return {
        "type": "function",
        "function": {
            "name": "Tasks",
            "description": tasks_tool.short_desc,
            "parameters": tasks_tool.llm_schema(),
        },
    }


def python_cmd(description: str) -> dict[str, Any]:
    """Build Python command schema with dynamic workspace description."""
    return {
        "type": "function",
        "function": {
            "name": "Python",
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to execute.",
                    },
                },
                "required": ["code"],
            },
        },
    }
