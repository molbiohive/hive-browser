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
    """Execution orchestrator for the built-in python sandbox."""

    def __init__(
        self,
        workspace: Workspace,
        output_limit: int = 4000,
        registry: ToolRegistry | None = None,
        tool_call_budget: int = 40,
    ):
        self.workspace = workspace
        self.output_limit = output_limit
        self.report: dict[str, Any] = {}
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
                    _tool.execute(dict(kwargs)),
                    loop,
                )
                return future.result(timeout=30)

            callables[tool.name] = wrapper
        return callables

    def _tool_signatures(self) -> str:
        """Callable tools listing: name(params)."""
        if not self._registry:
            return ""
        tools = self._registry.tools()
        if not tools:
            return ""
        lines = ["Callable tools (use keyword args):"]
        for tool in tools:
            schema = tool.input_schema()
            props = schema.get("properties", {})
            params = ", ".join(props.keys())
            lines.append(f"  {tool.name}({params})")
        return "\n".join(lines)

    def tool_schema(self) -> dict:
        """OpenAI-format function schema with dynamic workspace description."""
        desc = self.workspace.describe(report=self.report)
        sigs = self._tool_signatures()
        if sigs:
            desc += f"\n{sigs}"
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
        variables = dict(self.workspace.user_vars)
        variables.update(self.workspace.namespace())
        variables["report"] = self.report
        if self._registry:
            variables.update(self._make_tool_callables(loop))
        result = await asyncio.to_thread(safe_exec, code, variables)
        if result["status"] == "ok" and result.get("user_vars"):
            self.workspace.update_vars(result["user_vars"])
        return result

    def flush_report(self) -> None:
        """Move report entries to r<N> workspace handles."""
        for key, val in self.report.items():
            self.workspace.store(key, val, "report", prefix="r")

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

        if isinstance(value, (list, dict)):
            text = json.dumps(value, default=str)
            if len(text) > max_chars:
                text = text[: max_chars - 3] + "..."
        else:
            text = str(value)

        parts = [f"feedback = {text}"]
        if stdout:
            parts.append(f"stdout: {stdout.rstrip()}")
        return "\n".join(parts)
