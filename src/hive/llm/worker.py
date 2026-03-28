"""Worker agent -- agentic loop that executes tool calls via sandbox."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from hive.context import current_chat_tasks
from hive.llm.base import LLMAgent
from hive.sandbox import SandboxRunner, Workspace
from hive.tools import ToolRegistry

if TYPE_CHECKING:
    from hive.llm.client import LLMClient

logger = logging.getLogger(__name__)

_SYSTEM = """\
You are Hive Browser, a lab sequence search assistant. Be FAST and DIRECT.

## Priority: speed over depth
- Answer in 1-3 tool calls. Search -> summarize -> done.
- Show what was asked. Do NOT add unsolicited deep analysis.
- If user asks "what plasmids do we have" -> search, build a table, respond.
- Never loop trying to perfect results. Good enough is good enough.
- If a python call errors, fix it ONCE. If it errors again, respond with what you have.

## Tools
- tasks(action, text, task_id) -- manage the chat task list.
- python(code) -- run Python on workspace data. All tools (search, blast, profile, parts, ...) are callable inside python.

## Sandbox
- MUST assign `feedback = "short caption"`.
- `report["key"] = list_of_dicts` -> table widget for user.
- Handles (p0, p1, ...) are pre-injected as variables.
- No import/exec/eval/open. Builtins only: len, sum, min, max, sorted, reversed,
  enumerate, zip, range, filter, map, any, all, isinstance, int, float, str, bool,
  list, dict, tuple, set, next, iter, repr, hasattr, getattr, print.
- Variables persist across python calls within one message.
- Use desc(var) to inspect data structure when unsure about keys/types.

## Identifiers
SID = Sequence ID. PID = Part ID (canonical across files).
Tools accept raw sequence, sid:N, or pid:N.

## Workspace
Results stored as p0, p1, ... (current message) and r0, r1, ... (persist).
report["key"] = data -> widget. feedback = caption (required).

## Rules
- Never fabricate data. Use blast for sequence similarity, not search.
- After tools: 1-2 sentences. Never restate items the user can see in a table.
- Do NOT call tools for greetings or general questions."""

_SUMMARY_PROMPT = """\
Write a 1-3 sentence summary of what you found for the user. \
Do NOT repeat table data -- the user can see it in the widget. \
Be concise and direct."""


def system_prompt() -> str:
    """Return the worker system prompt (used by tests)."""
    return _SYSTEM


class Worker(LLMAgent):
    """Execution agent -- runs the agentic tool loop.

    LLM sees exactly 2 tools: tasks (function-calling) + python (sandbox).
    All registered tools are callable from python code inside the sandbox.
    Messages are rebuilt from scratch each turn (flat context via workspace).
    """

    def __init__(
        self,
        registry: ToolRegistry,
        workspace: Workspace,
        output_limit: int = 4000,
        tool_call_budget: int = 100,
    ):
        super().__init__()
        self._registry = registry
        self._workspace = workspace
        self._output_limit = output_limit
        self._tool_call_budget = tool_call_budget
        # Per-run context (set via prepare)
        self._user_input = ""
        self._plan: str | None = None
        self._history: list[dict] | None = None
        self._on_progress: Callable[[dict], Awaitable[None]] | None = None
        # Per-run state (reset in _reset)
        self._chain: list[dict] = []
        self._error: str = ""
        self._last_result: dict | None = None
        self._last_tool: str | None = None
        self._last_params: dict = {}
        self._last_feedback: str = ""
        self._sandbox: SandboxRunner | None = None

    def prepare(
        self,
        user_input: str,
        plan: str | None = None,
        history: list[dict] | None = None,
        on_progress: Callable[[dict], Awaitable[None]] | None = None,
    ) -> Worker:
        """Set context for the next run."""
        self._user_input = user_input
        self._plan = plan
        self._history = history
        self._on_progress = on_progress
        return self

    # -- State --

    def _reset(self):
        super()._reset()
        self._chain = []
        self._error = ""
        self._last_result = None
        self._last_tool = None
        self._last_params = {}
        self._last_feedback = ""
        self._workspace.reset_loop()
        self._sandbox = SandboxRunner(
            self._workspace,
            output_limit=self._output_limit,
            registry=self._registry,
            tool_call_budget=self._tool_call_budget,
        )

    # -- Hooks --

    async def _pre_run(self) -> None:
        await self._emit("thinking")

    def _build_messages(self) -> list[dict]:
        # System prompt -- include plan as part of system context
        system = _SYSTEM
        if self._plan:
            system += f"\n\n## Plan\n{self._plan}"

        task_ctx = self._task_context()
        if task_ctx:
            system += f"\n\n{task_ctx}"

        msgs: list[dict] = [{"role": "system", "content": system}]

        # History (only when no plan -- plan already contains resolved context)
        if not self._plan and self._history:
            msgs.extend(self._history)

        # User message with optional workspace context
        ws = self._workspace
        ws_ctx = ""
        if len(ws) > 0 and not ws.steps:
            ws_ctx = f"\n\n[Workspace]\n{ws.describe()}"
        msgs.append({"role": "user", "content": f"{self._user_input}{ws_ctx}"})

        # Progress from previous turns
        progress = ws.history()
        if progress:
            msgs.append({"role": "assistant", "content": f"Done so far:\n{progress}"})
            msgs.append({"role": "user", "content": "Continue."})

        return msgs

    def _tools(self) -> list[dict]:
        tasks_tool = self._registry.get("tasks")
        assert tasks_tool, "tasks tool must be registered"
        return [
            {
                "type": "function",
                "function": {
                    "name": "tasks",
                    "description": tasks_tool.short_desc,
                    "parameters": tasks_tool.llm_schema(),
                },
            },
            self._sandbox.tool_schema(),
        ]

    async def _on_error(self, error: Exception, turn: int) -> bool:
        sanitized = self._sanitize_error(str(error))
        if sanitized == "Rate limit reached":
            logger.warning("Rate limit hit (turn %d), retrying in 15s", turn)
            await asyncio.sleep(15)
            return True
        logger.error("LLM call failed (turn %d): %s", turn, error)
        self._error = sanitized
        return False

    async def _handle_call(self, tc: dict) -> None:
        tool_name = tc["function"]["name"]
        params = self._parse_tool_args(tc)

        args_raw = tc["function"].get("arguments", "{}")
        args_len = len(args_raw) if isinstance(args_raw, str) else len(json.dumps(args_raw))
        logger.debug("TOOL_CALL %s: args=%d chars", tool_name, args_len)

        if tool_name == "python":
            await self._exec_python(params)
        elif tool_name == "tasks":
            await self._exec_tasks(params)
        else:
            err = f"'{tool_name}' is callable from python: {tool_name}(param=value)"
            self._workspace.add_step(tool_name, err, error=err)

        await self._emit("tool", tool=tool_name)

    async def _post_turn(self, turn: int) -> None:
        pass

    def _on_complete(self, content: str) -> dict[str, Any]:
        logger.info(
            "Worker done after %d step(s): %s",
            len(self._chain), [s["tool"] for s in self._chain],
        )

        if self._sandbox.report:
            self._sandbox.flush_report()
            self._last_result = self._sandbox.report
            self._last_tool = "python"
            self._last_params = {"feedback": self._last_feedback} if self._last_feedback else {}

        if self._last_result and self._last_tool:
            resp = self._result(
                "tool_result", tool=self._last_tool, data=self._last_result,
                params=self._last_params, content=content, chain=self._chain,
            )
            if self._sandbox.report:
                resp["report"] = True
            return resp

        return self._result("message", content=content, chain=self._chain)

    async def _on_exhausted(self) -> dict[str, Any]:
        if not self._error:
            logger.warning(
                "Worker hit max turns: %s", [s["tool"] for s in self._chain],
            )

        if not self._chain:
            resp = self._result(
                "message",
                content=f"LLM error: {self._error}" if self._error
                else "No tools were called during reasoning.",
            )
            if self._error:
                resp["llm_error"] = True
            return resp

        # Has chain -- try final summary
        fallback = ""
        if not self._error:
            fallback = await self._final_summary()

        if not fallback:
            if self._error:
                fallback = f"Analysis stopped due to an error: {self._error}"
            elif self._last_feedback:
                fallback = self._last_feedback
            elif self._chain:
                fallback = self._chain[-1]["summary"]
            else:
                fallback = ""

        if self._sandbox.report:
            if not self._error:
                self._sandbox.flush_report()
            self._last_result = self._sandbox.report
            self._last_tool = "python"
            self._last_params = {"feedback": self._last_feedback} if self._last_feedback else {}

        if self._last_result and self._last_tool:
            resp = self._result(
                "tool_result", tool=self._last_tool, data=self._last_result,
                params=self._last_params, content=fallback, chain=self._chain,
            )
            if self._sandbox.report:
                resp["report"] = True
            if self._error:
                resp["llm_error"] = True
            return resp

        resp = self._result("message", content=fallback, chain=self._chain)
        if self._error:
            resp["llm_error"] = True
        return resp

    # -- Tool execution --

    async def _exec_python(self, params: dict) -> None:
        code = params.get("code", "")
        sb_result = await self._sandbox.execute(code)
        compact = self._sandbox.summary_for_llm(sb_result)
        ws = self._workspace

        if sb_result["status"] != "ok":
            err_text = sb_result.get("error", "unknown")
            hint = _error_hint(err_text, ws, self._sandbox)
            ws.add_step("python", err_text, code=code, error=err_text, hint=hint)
            display = f"Error: {err_text}"
        else:
            fb = str(sb_result.get("feedback", ""))[:100]
            self._last_feedback = fb
            produced = _build_produced(ws, self._sandbox)
            ws.add_step("python", fb, code=code, produced=produced)
            display = fb

        self._chain.append({"tool": "python", "params": {"code": code}, "summary": display})
        logger.info("Sandbox exec: %s", compact[:200])

    async def _exec_tasks(self, params: dict) -> None:
        tasks_tool = self._registry.get("tasks")
        result = await tasks_tool.execute(params)
        compact = tasks_tool.format_result(result)
        self._workspace.add_step("tasks", compact)
        self._chain.append({"tool": "tasks", "params": params, "summary": compact})
        logger.info("Worker tasks(%s)", json.dumps(params))

    # -- Final summary --

    async def _final_summary(self) -> str:
        """One last LLM call (no tools) to summarize results."""
        report_keys = list(self._sandbox.report.keys()) if self._sandbox.report else []
        steps = self._workspace.history()

        prompt = f"The user asked: {self._user_input}\n\nYou completed these steps:\n{steps}\n\n"
        if report_keys:
            prompt += f"Report sections ready: {', '.join(report_keys)}\n\n"
        prompt += _SUMMARY_PROMPT

        try:
            response = await self._chat(
                self._llm,
                [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": prompt},
                ],
            )
            return self._msg_content(response)
        except Exception as e:
            logger.warning("Final summary call failed: %s", e)
            return ""

    # -- Helpers --

    def _result(self, type_: str, **kwargs: Any) -> dict[str, Any]:
        """Build response dict with tokens and optional plan."""
        resp: dict[str, Any] = {"type": type_}
        for k, v in kwargs.items():
            if v is not None:
                resp[k] = v
        resp["tokens"] = dict(self.tokens)
        if self._plan:
            resp["plan"] = self._plan
        return resp

    async def _emit(self, phase: str, **extra: Any) -> None:
        if self._on_progress:
            data: dict[str, Any] = {
                "phase": phase,
                "tools_used": len(self._chain),
                "tokens": dict(self.tokens),
                **extra,
            }
            await self._on_progress(data)

    @staticmethod
    def _task_context() -> str:
        chat_tasks = current_chat_tasks.get()
        if not chat_tasks:
            return ""
        lines = []
        for t in chat_tasks:
            mark = "x" if t.get("done") else " "
            lines.append(f"- [{mark}] {t.get('text', '')}")
        return "Current tasks:\n" + "\n".join(lines)


# -- Module-level helpers --


def _error_hint(err_text: str, workspace: Workspace, sandbox: SandboxRunner) -> str | None:
    m = re.search(r"KeyError:?\s*['\"](\w+)['\"]", err_text)
    if m:
        for e in reversed(workspace._entries):
            if isinstance(e.value, list) and e.value and isinstance(e.value[0], dict):
                keys = ", ".join(list(e.value[0].keys())[:8])
                return f"keys: {{{keys}}}"
        return None

    m = re.search(r"NameError:?\s*.*?'(\w+)'", err_text)
    if m:
        ns = list(workspace.namespace().keys())
        uv = list(workspace.user_vars.keys())
        available = ns + uv + list(sandbox.report.keys())
        if available:
            return f"available: {', '.join(available[:10])}"
    return None


def _build_produced(workspace: Workspace, sandbox: SandboxRunner) -> str | None:
    parts: list[str] = []
    if sandbox.report:
        rkeys = list(sandbox.report.keys())
        if rkeys:
            parts.append(f"report[{', '.join(repr(k) for k in rkeys[-2:])}]")
    uv = workspace.user_vars
    if uv:
        names = list(uv.keys())[-3:]
        parts.append(", ".join(names))
    return ", ".join(parts) if parts else None
