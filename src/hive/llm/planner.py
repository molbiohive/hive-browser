"""Planner agent -- produces a task plan for the worker."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from hive.llm.base import LLMAgent

if TYPE_CHECKING:
    from hive.llm.client import LLMClient
    from hive.skills import SkillLibrary
    from hive.tools import ToolRegistry

logger = logging.getLogger(__name__)

_SYSTEM = """\
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
Call search() to see available domain procedures.
Call read(name) for procedures matching the user's request.
Use the procedure's workflow, report keys, and pitfalls in your brief.
If no procedure matches, produce the brief from the tool catalog alone.

## Rules
- Resolve all references ("that plasmid", "those results") to concrete \
IDs/names/values from conversation history. Never leave pronouns unresolved.
- Each DELIVER step = one report table or one answer the user expects to see.
- Be specific about columns/fields the user cares about.
- For greetings/chat/general questions: write only "GOAL: respond conversationally".
- NEVER fabricate data, IDs, or results.
- Keep it tight -- the brief is injected into the worker's system prompt."""

_TOOLS = [
    {"type": "function", "function": {
        "name": "search",
        "description": "List available skill procedures with trigger descriptions.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "read",
        "description": "Read full content of a skill procedure by name.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "Skill name"},
        }, "required": ["name"]},
    }},
]


class Planner(LLMAgent):
    """Plan generation agent.

    Multi-turn loop that reads the tool catalog, consults skill
    procedures via search/read tools, and produces a self-contained
    task description for the worker.
    """

    def __init__(self, registry: ToolRegistry, skills: SkillLibrary):
        super().__init__()
        sigs = registry.signatures(detailed=True)
        self._catalog = "\n".join(f"- {s}" for s in sigs)
        self._skills = skills
        self._user_input = ""
        self._history: list[dict] | None = None
        self._search_result: list[dict] | None = None
        self._read_skills: list[dict] = []

    def _reset(self):
        super()._reset()
        self._search_result = None
        self._read_skills = []

    def prepare(
        self,
        user_input: str,
        history: list[dict] | None = None,
    ) -> Planner:
        """Set context for the next run."""
        self._user_input = user_input
        self._history = history
        return self

    def _tools(self) -> list[dict]:
        return _TOOLS

    async def _handle_call(self, tc: dict) -> None:
        name = tc["function"]["name"]
        args = self._parse_tool_args(tc)
        if name == "search":
            self._search_result = self._skills.catalog()
        elif name == "read":
            skill_name = args.get("name", "")
            content = self._skills.read(skill_name)
            if content:
                self._read_skills.append({"name": skill_name, "content": content})

    def _build_messages(self) -> list[dict]:
        system = _SYSTEM.format(catalog=self._catalog)

        if self._search_result is not None:
            lines = [f"- **{s['name']}**: {s['when']}" for s in self._search_result]
            system += "\n\n## Available Skills\n" + "\n".join(lines)
        if self._read_skills:
            parts = [f"### {s['name']}\n{s['content']}" for s in self._read_skills]
            system += "\n\n## Domain Skills\n" + "\n".join(parts)

        messages: list[dict] = [{"role": "system", "content": system}]
        if self._history:
            messages.extend(self._history)
        messages.append({"role": "user", "content": self._user_input})
        return messages

    def _on_complete(self, content: str) -> tuple[str, dict[str, int]]:
        return content, dict(self.tokens)

    async def _on_exhausted(self) -> tuple[str, dict[str, int]]:
        return "", dict(self.tokens)
