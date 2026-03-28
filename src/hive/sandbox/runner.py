"""SandboxRunner -- orchestrates workspace + exec, provides tool schema."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from hive.sandbox.exec import safe_exec
from hive.sandbox.workspace import Workspace, detailed_describe

if TYPE_CHECKING:
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
        ws = self.workspace
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
                result = future.result(timeout=30)
                # Build provenance call_repr and auto-store in workspace
                args_str = ", ".join(
                    f'{k}="{v}"' if isinstance(v, str) else f"{k}={v}"
                    for k, v in kwargs.items()
                )
                call_repr = f"{_tool.name}({args_str})"
                if isinstance(result, dict):
                    ws.store_result(result, _tool.name, dict(kwargs), call_repr=call_repr)
                return result

            callables[tool.name] = wrapper
        return callables

    def _make_desc_fn(self) -> Any:
        """Build desc() — detailed inspection, results shown in workspace."""
        ws = self.workspace

        def desc(var, name="?"):
            detail = detailed_describe(var)
            ws.add_desc_result(name, detail)
            return detail

        return desc

    def _tool_signatures(self) -> list[str]:
        """One-per-line typed tool listing for describe() Available section."""
        lines: list[str] = []
        if self._registry:
            for tool in self._registry.tools():
                schema = tool.llm_schema()
                props = schema.get("properties", {})
                required = set(schema.get("required", []))
                req_parts = []
                opt_parts = []
                for name, spec in props.items():
                    typ = spec.get("type", "any")
                    typed = f"{name}:{typ}"
                    if name in required:
                        req_parts.append(typed)
                    else:
                        opt_parts.append(typed)
                params = ", ".join(req_parts)
                if opt_parts:
                    params += f" [{', '.join(opt_parts)}]" if params else f"[{', '.join(opt_parts)}]"
                lines.append(f"{tool.name}({params}) -- {tool.short_desc}")
        lines.append("desc(var) -- inspect variable")
        return lines

    def tool_schema(self) -> dict:
        """OpenAI-format function schema with dynamic workspace description."""
        sigs = self._tool_signatures()
        desc = self.workspace.describe(report=self.report, tool_signatures=sigs)
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
        """Run *code* with workspace handles + report dict + persisted vars + tool callables + desc()."""
        loop = asyncio.get_running_loop()
        variables = dict(self.workspace.user_vars)
        variables.update(self.workspace.namespace())
        variables["report"] = self.report
        variables["desc"] = self._make_desc_fn()
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
