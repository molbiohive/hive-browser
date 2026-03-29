"""Unified agent -- single agentic loop with planner/worker modes."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from hive.context import current_chat_tasks
from hive.llm.base import LLMAgent
from hive.llm.commands import PLAN_CMD, PLANNER_CMDS, python_cmd, tasks_cmd
from hive.sandbox import SandboxRunner, Workspace
from hive.tools import ToolRegistry

if TYPE_CHECKING:
    from hive.llm.client import LLMClient
    from hive.skills import SkillLibrary

logger = logging.getLogger(__name__)

# -- System prompts --

_PLANNER_SYSTEM = """\
You are a brief producer for a lab sequence browser's worker agent.

The worker has these tools (callable from Python):
{catalog}

The worker renders results via `report["key"] = list_of_dicts` (table widget).

Your job: produce a SELF-CONTAINED brief. The worker will NOT see conversation \
history -- your brief must carry all context it needs.

## Brief format

GOAL: What the user wants (one sentence).
CONTEXT: Resolved references from history -- concrete IDs, names, values. \
Only include what the worker needs. Omit if first message.
DELIVER:
1. Step with expected report key and columns, e.g. \
report["plasmids"]: name, size_bp, resistance
2. Next step ...
STOP: What NOT to do -- no unsolicited extras.

## Skills
Call Search() to browse available domain procedures.
Call Read(name) to load a procedure matching the user's request.
Use the procedure's workflow, report keys, and pitfalls in your brief.
For greetings/general questions, skip tools and respond directly.

## Rules
- Resolve all references ("that plasmid", "those results") to concrete \
IDs/names/values from conversation history. Never leave pronouns unresolved.
- Each DELIVER step = one report table or one answer the user expects to see.
- Be specific about columns/fields the user cares about.
- For greetings/chat/general questions: write only "GOAL: respond conversationally".
- NEVER fabricate data, IDs, or results.
- Keep it tight -- the brief is injected into the worker's system prompt."""

_WORKER_SYSTEM = """\
You are Hive Browser, a lab sequence search assistant. Be FAST and DIRECT.

## Priority: speed over depth
- Answer in 1-3 tool calls. Search -> summarize -> done.
- Show what was asked. Do NOT add unsolicited deep analysis.
- If user asks "what plasmids do we have" -> search, build a table, respond.
- Never loop trying to perfect results. Good enough is good enough.
- If a python call errors, fix it ONCE. If it errors again, respond with what you have.

## Tools
- Tasks(action, text, task_id) -- manage the chat task list.
- Python(code) -- run Python on workspace data. All tools (search, blast, profile, \
parts, ...) are callable inside python.
- Plan() -- switch to planner mode to research skills.

## Sandbox
- `report["key"] = list_of_dicts` -> table widget for user.
- No import/exec/eval/open. Builtins only: len, sum, min, max, sorted, reversed,
  enumerate, zip, range, filter, map, any, all, isinstance, int, float, str, bool,
  list, dict, tuple, set, next, iter, repr, hasattr, getattr, print.
- Variables persist across python calls within one message.
- Use desc(var) to inspect data structure when unsure about keys/types.

## Identifiers
SID = Sequence ID. PID = Part ID (canonical across files).
Tools accept raw sequence, sid:N, or pid:N.

## Rules
- Never fabricate data. Use blast for sequence similarity, not search.
- After tools: 1-2 sentences. Never restate items the user can see in a table.
- Do NOT call tools for greetings or general questions."""

_SUMMARY_PROMPT = """\
Write a 1-3 sentence summary of what you found for the user. \
Do NOT repeat table data -- the user can see it in the widget. \
Be concise and direct."""

_MAX_PLANNER_TURNS = 4


class Agent(LLMAgent):
    """Unified agent with planner/worker mode switching.

    The planner reads skills and produces a brief. The worker executes
    tools via sandbox and produces results. Mode switching happens
    automatically: planner text -> worker, Plan() command -> planner.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        skills: SkillLibrary | None = None,
        output_limit: int = 4000,
        tool_call_budget: int = 100,
    ):
        super().__init__()
        self._registry = registry
        self._skills = skills
        self._output_limit = output_limit
        self._tool_call_budget = tool_call_budget
        # Per-run context (via prepare)
        self._user_input = ""
        self._history: list[dict] | None = None
        self._on_progress: Callable[[dict], Awaitable[None]] | None = None
        self._use_planner = True
        # Per-run state (via _reset)
        self._mode = "planner"
        self._plan: str | None = None
        self._chain: list[dict] = []
        self._error = ""
        self._workspace: Workspace | None = None
        self._sandbox: SandboxRunner | None = None
        # Planner state
        self._catalog = ""
        self._read_skills: list[dict] = []
        self._conv: list[dict] = []
        self._turn_calls: list[dict] = []
        self._turn_results: list[dict] = []
        self._planner_turns = 0

    def prepare(
        self,
        user_input: str,
        history: list[dict] | None = None,
        on_progress: Callable[[dict], Awaitable[None]] | None = None,
        use_planner: bool = True,
    ) -> Agent:
        """Set context for the next run."""
        self._user_input = user_input
        self._history = history
        self._on_progress = on_progress
        self._use_planner = use_planner
        return self

    def _reset(self):
        super()._reset()
        # Mode
        if self._use_planner and self._skills and len(self._skills) > 0:
            self._mode = "planner"
        else:
            self._mode = "worker"
        # Worker state
        self._plan = None
        self._chain = []
        self._error = ""
        self._workspace = Workspace()
        self._sandbox = SandboxRunner(
            self._workspace,
            output_limit=self._output_limit,
            registry=self._registry,
            tool_call_budget=self._tool_call_budget,
        )
        # Planner state
        sigs = self._registry.signatures(detailed=True)
        self._catalog = "\n".join(f"- {s}" for s in sigs)
        self._read_skills = []
        self._conv = []
        self._turn_calls = []
        self._turn_results = []
        self._planner_turns = 0

    # -- Override run() for mode switching --

    async def run(self, llm: LLMClient, max_turns: int = 30) -> Any:
        """Run the unified agentic loop with planner/worker mode switching."""
        self._reset()
        self._llm = llm
        await self._pre_run()

        for turn in range(max_turns):
            messages = self._build_messages()
            tools = self._tools()
            tool_choice = self._tool_choice(turn)

            try:
                response = await self._chat(llm, messages, tools, tool_choice=tool_choice)
            except Exception as e:
                if self._mode == "planner":
                    # Planner failure -> switch to worker without plan
                    logger.warning("Planner LLM call failed, switching to worker: %s", e)
                    self._mode = "worker"
                    continue
                if await self._on_error(e, turn):
                    continue
                break

            finish = response["choices"][0].get("finish_reason", "")
            if finish == "refusal":
                content = self._msg_content(response)
                return self._on_complete(content or "Request declined by the model.")

            calls = self._msg_tool_calls(response)

            if self._mode == "planner":
                if not calls:
                    # Planner produced text -> that's the plan
                    self._plan = self._msg_content(response)
                    self._mode = "worker"
                    logger.info("Planner done, plan=%r", (self._plan or "")[:120])
                    continue  # Don't return -- keep looping in worker mode
                # Handle planner tool calls
                for tc in calls:
                    await self._handle_call(tc)
                await self._post_turn(turn)
                self._planner_turns += 1
                if self._planner_turns >= _MAX_PLANNER_TURNS:
                    logger.warning("Planner hit max turns, switching to worker")
                    self._mode = "worker"
                continue

            # Worker mode
            if not calls:
                return self._on_complete(self._msg_content(response))

            for tc in calls:
                await self._handle_call(tc)

            await self._post_turn(turn)

        return await self._on_exhausted()

    # -- Hooks --

    async def _pre_run(self) -> None:
        await self._emit("thinking")

    def _build_messages(self) -> list[dict]:
        if self._mode == "planner":
            return self._build_planner_messages()
        return self._build_worker_messages()

    def _tools(self) -> list[dict]:
        if self._mode == "planner":
            return PLANNER_CMDS
        return self._build_worker_tools()

    def _tool_choice(self, turn: int) -> str | None:
        if self._mode == "planner" and self._planner_turns == 0:
            return "required"
        return None

    async def _handle_call(self, tc: dict) -> None:
        name = tc["function"]["name"]
        if name == "Search":
            self._cmd_search(tc)
        elif name == "Read":
            self._cmd_read(tc)
        elif name == "Tasks":
            await self._cmd_tasks(tc)
        elif name == "Python":
            await self._cmd_python(tc)
        elif name == "Plan":
            self._cmd_plan()
        else:
            err = f"'{name}' is callable from python: {name}(param=value)"
            self._workspace.add_step(name, err, error=err)
        await self._emit("tool", tool=name)

    async def _post_turn(self, turn: int) -> None:
        if self._mode == "planner" and self._turn_calls:
            self._conv.append({
                "role": "assistant",
                "content": None,
                "tool_calls": list(self._turn_calls),
            })
            self._conv.extend(self._turn_results)
            self._turn_calls = []
            self._turn_results = []

    async def _on_error(self, error: Exception, turn: int) -> bool:
        sanitized = self._sanitize_error(str(error))
        if sanitized == "Rate limit reached":
            logger.warning("Rate limit hit (turn %d), retrying in 15s", turn)
            await asyncio.sleep(15)
            return True
        logger.error("LLM call failed (turn %d): %s", turn, error)
        self._error = sanitized
        return False

    def _on_complete(self, content: str) -> dict[str, Any]:
        logger.info(
            "Agent done after %d step(s): %s",
            len(self._chain), [s["tool"] for s in self._chain],
        )

        if self._sandbox.report:
            self._sandbox.flush_report()

        if self._sandbox.report:
            resp = self._result(
                "tool_result", tool="python", data=self._sandbox.report,
                params={}, content=content, chain=self._chain,
            )
            resp["report"] = True
            return resp

        return self._result("message", content=content, chain=self._chain)

    async def _on_exhausted(self) -> dict[str, Any]:
        if not self._error:
            logger.warning(
                "Agent hit max turns: %s", [s["tool"] for s in self._chain],
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
            elif self._chain:
                fallback = self._chain[-1]["summary"]
            else:
                fallback = ""

        if self._sandbox.report:
            if not self._error:
                self._sandbox.flush_report()

        if self._sandbox.report:
            resp = self._result(
                "tool_result", tool="python", data=self._sandbox.report,
                params={}, content=fallback, chain=self._chain,
            )
            resp["report"] = True
            if self._error:
                resp["llm_error"] = True
            return resp

        resp = self._result("message", content=fallback, chain=self._chain)
        if self._error:
            resp["llm_error"] = True
        return resp

    # -- Message building --

    def _build_planner_messages(self) -> list[dict]:
        system = _PLANNER_SYSTEM.format(catalog=self._catalog)

        if self._read_skills:
            parts = [f"### {s['name']}\n{s['content']}" for s in self._read_skills]
            system += "\n\n## Domain Skills\n" + "\n".join(parts)

        messages: list[dict] = [{"role": "system", "content": system}]
        if self._history:
            messages.extend(self._history)
        messages.append({"role": "user", "content": self._user_input})

        # Append tool call conversation so model sees its past actions
        messages.extend(self._conv)

        return messages

    def _build_worker_messages(self) -> list[dict]:
        system = _WORKER_SYSTEM
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
        if ws.user_vars and not ws.steps:
            ws_ctx = f"\n\n[Workspace]\n{ws.describe()}"
        msgs.append({"role": "user", "content": f"{self._user_input}{ws_ctx}"})

        # Progress from previous turns
        progress = ws.history()
        if progress:
            msgs.append({"role": "assistant", "content": f"Done so far:\n{progress}"})
            msgs.append({"role": "user", "content": "Continue."})

        return msgs

    def _build_worker_tools(self) -> list[dict]:
        tools = []
        tasks_tool = self._registry.get("tasks")
        if tasks_tool:
            tools.append(tasks_cmd(tasks_tool))
        tools.append(self._sandbox.tool_schema())
        # Rename python -> Python for consistency with commands
        tools[-1]["function"]["name"] = "Python"
        if self._skills and len(self._skills) > 0:
            tools.append(PLAN_CMD)
        return tools

    # -- Planner commands --

    def _cmd_search(self, tc: dict) -> None:
        self._turn_calls.append(tc)
        cat = self._skills.catalog() if self._skills else []
        result_content = (
            "\n".join(f"- {s['name']}: {s['when']}" for s in cat)
            if cat else "No skills available."
        )
        logger.info("Agent/planner: search returned %d skills", len(cat))
        self._turn_results.append({
            "role": "tool",
            "tool_call_id": tc.get("id", ""),
            "content": result_content,
        })

    def _cmd_read(self, tc: dict) -> None:
        self._turn_calls.append(tc)
        args = self._parse_tool_args(tc)
        skill_name = args.get("name", "")
        content = self._skills.read(skill_name) if self._skills else None
        if content:
            self._read_skills.append({"name": skill_name, "content": content})
            result_content = content
            logger.info("Agent/planner: read skill %r (%d chars)", skill_name, len(content))
        else:
            available = ", ".join(self._skills.names()) if self._skills else ""
            result_content = f"Skill '{skill_name}' not found. Available: {available}"
            logger.warning("Agent/planner: skill %r not found", skill_name)
        self._turn_results.append({
            "role": "tool",
            "tool_call_id": tc.get("id", ""),
            "content": result_content,
        })

    # -- Worker commands --

    async def _cmd_tasks(self, tc: dict) -> None:
        params = self._parse_tool_args(tc)
        tasks_tool = self._registry.get("tasks")
        result = await tasks_tool.execute(params)
        compact = tasks_tool.format_result(result)
        self._workspace.add_step("tasks", compact)
        self._chain.append({"tool": "tasks", "params": params, "summary": compact})
        logger.info("Agent tasks(%s)", json.dumps(params))

    async def _cmd_python(self, tc: dict) -> None:
        params = self._parse_tool_args(tc)
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
            produced = _build_produced(ws, self._sandbox)
            ws.add_step("python", compact, code=code, produced=produced)
            display = compact

        self._chain.append({"tool": "python", "params": {"code": code}, "summary": display})
        logger.info("Sandbox exec: %s", compact[:200])

    def _cmd_plan(self) -> None:
        """Switch back to planner mode."""
        logger.info("Agent: Plan() called, switching to planner mode")
        self._mode = "planner"
        self._planner_turns = 0
        self._conv = []
        self._turn_calls = []
        self._turn_results = []

    # -- Final summary --

    async def _final_summary(self) -> str:
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
                    {"role": "system", "content": _WORKER_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
            )
            return self._msg_content(response)
        except Exception as e:
            logger.warning("Final summary call failed: %s", e)
            return ""

    # -- Helpers --

    def _result(self, type_: str, **kwargs: Any) -> dict[str, Any]:
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
        for val in reversed(list(workspace.user_vars.values())):
            if isinstance(val, list) and val and isinstance(val[0], dict):
                keys = ", ".join(list(val[0].keys())[:8])
                return f"keys: {{{keys}}}"
        return None

    m = re.search(r"NameError:?\s*.*?'(\w+)'", err_text)
    if m:
        uv = list(workspace.user_vars.keys())
        available = uv + list(sandbox.report.keys())
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
