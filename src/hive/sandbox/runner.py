"""SandboxRunner -- orchestrates workspace + exec, provides tool schema."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from hive.sandbox.exec import safe_exec
from hive.sandbox.workspace import Workspace

if TYPE_CHECKING:
    from hive.tools.base import ToolRegistry

logger = logging.getLogger(__name__)


class SandboxRunner:
    """Execution orchestrator for the built-in python sandbox.

    Not a Tool -- this is a server-side runtime capability injected
    by the router alongside regular tool schemas.
    """

    def __init__(
        self,
        workspace: Workspace,
        output_limit: int = 4000,
        registry: ToolRegistry | None = None,
        tool_call_budget: int = 40,
    ):
        self.workspace = workspace
        self.output_limit = output_limit
        self.report: dict[str, Any] = {}  # LLM-populated, persists across calls
        self._user_vars: dict[str, Any] = {}  # variables from previous python calls
        self._registry = registry
        self._tool_call_budget = tool_call_budget

    def _make_tool_callables(self, loop: asyncio.AbstractEventLoop) -> dict[str, Any]:
        """Build sync wrapper functions for each registered tool."""
        if not self._registry:
            return {}
        callables: dict[str, Any] = {}
        budget = self._tool_call_budget
        call_count = [0]

        for tool in self._registry.tools():

            def wrapper(_tool=tool, **kwargs):
                call_count[0] += 1
                if call_count[0] > budget:
                    raise RuntimeError(f"Tool call budget exceeded ({budget})")
                future = asyncio.run_coroutine_threadsafe(
                    _tool.execute(dict(kwargs)), loop,
                )
                result = future.result(timeout=30)
                if "error" not in result:
                    self.workspace.store_result(result, _tool.name, dict(kwargs))
                return result

            callables[tool.name] = wrapper
        return callables

    def _tool_signatures(self) -> str:
        """Compact listing of callable tools for the python schema description.

        Includes param names, types, and descriptions from input_schema().
        """
        if not self._registry:
            return ""
        tools = self._registry.tools()
        if not tools:
            return ""
        lines = ["Callable tools:"]
        for tool in tools:
            schema = tool.input_schema()
            props = schema.get("properties", {})
            params = ", ".join(
                f"{name}: {spec.get('type', 'any')}" for name, spec in props.items()
            )
            param_descs = []
            for name, spec in props.items():
                if d := spec.get("description"):
                    param_descs.append(f"{name}={d}")
            extra = f" ({', '.join(param_descs)})" if param_descs else ""
            lines.append(f"  {tool.name}({params}) -- {tool.description}{extra}")
        return "\n".join(lines)

    def tool_schema(self) -> dict:
        """OpenAI-format function schema with dynamic workspace description."""
        desc = (
            "Execute Python on cached data. Variables in scope:\n"
            + self.workspace.describe_all()
            + "\n`report` dict accumulates widget data. "
            "Assign named values: report[\"features\"] = [...].\n"
            "Must assign to `feedback` (caption text for the widget)."
        )
        sigs = self._tool_signatures()
        if sigs:
            desc += f"\n{sigs}"
        if self._user_vars:
            names = ", ".join(sorted(self._user_vars))
            desc += f"\nPersisted variables from previous calls: {names}"
        return {
            "type": "function",
            "function": {
                "name": "python",
                "description": desc,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Python code. Assign output to `feedback`.",
                        },
                    },
                    "required": ["code"],
                },
            },
        }

    async def execute(self, code: str) -> dict[str, Any]:
        """Run *code* with workspace handles + report dict + persisted vars + tool callables."""
        loop = asyncio.get_running_loop()
        variables = dict(self._user_vars)  # start with persisted user variables
        variables.update(self.workspace.namespace())  # workspace handles win
        variables["report"] = self.report  # mutable dict — changes persist
        if self._registry:
            variables.update(self._make_tool_callables(loop))
        result = await asyncio.to_thread(safe_exec, code, variables)
        if result["status"] == "ok" and result.get("user_vars"):
            self._user_vars.update(result["user_vars"])
        return result

    def summary_for_llm(self, result: dict[str, Any]) -> str:
        """Compact result summary for LLM context."""
        if result["status"] == "error":
            parts = [f"Error: {result['error']}"]
            if result.get("stdout"):
                parts.append(f"stdout: {result['stdout'].rstrip()}")
            return "\n".join(parts)

        value = result["feedback"]
        stdout = result.get("stdout", "")
        max_chars = self.output_limit

        # Format the feedback value
        if isinstance(value, (list, dict)):
            text = json.dumps(value, default=str)
            if len(text) > max_chars:
                text = text[:max_chars - 3] + "..."
        else:
            text = str(value)

        parts = [f"feedback = {text}"]
        if stdout:
            parts.append(f"stdout: {stdout.rstrip()}")
        return "\n".join(parts)
