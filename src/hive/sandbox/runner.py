"""SandboxRunner -- orchestrates workspace + exec, provides tool schema."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from hive.sandbox.exec import safe_exec
from hive.sandbox.workspace import detailed_describe

if TYPE_CHECKING:
    from hive.sandbox.workspace import Workspace
    from hive.tools import ToolRegistry

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

        def _make_wrapper(t):
            def wrapper(*args, **kwargs):
                # Accept first positional arg as 'query' for convenience
                if args:
                    schema = t.llm_schema()
                    required = schema.get("required", [])
                    first_param = required[0] if required else next(iter(schema.get("properties", {})), None)
                    if first_param and first_param not in kwargs:
                        kwargs[first_param] = args[0]
                call_count[0] += 1
                if call_count[0] > budget:
                    raise RuntimeError(f"Tool call budget exceeded ({budget})")
                future = asyncio.run_coroutine_threadsafe(
                    t.execute(dict(kwargs)),
                    loop,
                )
                return future.result(timeout=30)
            return wrapper

        for tool in self._registry.tools():
            callables[tool.name] = _make_wrapper(tool)
        return callables

    def _make_desc_fn(self) -> Any:
        """Build desc() -- detailed inspection, results shown in workspace."""
        ws = self.workspace

        def desc(var, name="?"):
            detail = detailed_describe(var)
            ws.add_desc_result(name, detail)
            return detail

        return desc

    def tool_schema(self) -> dict:
        """OpenAI-format function schema with dynamic workspace description."""
        sigs = self._registry.signatures() if self._registry else []
        sigs.append("desc(var, name: str | None = None) -> str  # inspect variable")
        ws_desc = self.workspace.describe(report=self.report, tool_signatures=sigs)
        return {
            "type": "function",
            "function": {
                "name": "python",
                "description": ws_desc,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "description": {
                            "type": "string",
                            "description": "Brief description of what this code does.",
                        },
                        "code": {
                            "type": "string",
                            "description": "Python code to execute.",
                        },
                    },
                    "required": ["description", "code"],
                },
            },
        }

    async def execute(self, code: str) -> dict[str, Any]:
        """Run *code* with user vars + report dict + tool callables + desc()."""
        loop = asyncio.get_running_loop()
        variables = dict(self.workspace.user_vars)
        variables["report"] = self.report
        variables["desc"] = self._make_desc_fn()
        if self._registry:
            variables.update(self._make_tool_callables(loop))
        result = await asyncio.to_thread(safe_exec, code, variables)
        if result.get("user_vars"):
            self.workspace.update_vars(result["user_vars"])
        return result

    def flush_report(self) -> None:
        """Mark report as flushed (no-op now that handles are removed)."""

    def summary_for_llm(self, result: dict[str, Any]) -> str:
        """Compact result summary for LLM context."""
        if result["status"] == "error":
            parts = [f"Error: {result['error']}"]
            if result.get("stdout"):
                parts.append(f"stdout: {result['stdout'].rstrip()}")
            return "\n".join(parts)

        parts: list[str] = []
        stdout = result.get("stdout", "")

        # Show new/modified variable names and shapes
        user_vars = result.get("user_vars", {})
        if user_vars:
            var_summaries = []
            for k, v in list(user_vars.items())[:5]:
                if isinstance(v, list):
                    var_summaries.append(f"{k}: list({len(v)})")
                elif isinstance(v, dict):
                    var_summaries.append(f"{k}: dict({len(v)})")
                elif isinstance(v, str) and len(v) > 40:
                    var_summaries.append(f"{k}: str({len(v)})")
                else:
                    var_summaries.append(f"{k} = {repr(v)}")
            parts.append("vars: " + ", ".join(var_summaries))

        if stdout:
            trimmed = stdout.rstrip()
            if len(trimmed) > self.output_limit:
                trimmed = trimmed[: self.output_limit - 3] + "..."
            parts.append(f"stdout: {trimmed}")

        return "\n".join(parts) if parts else "ok"
