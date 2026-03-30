"""Tests for the unified Agent: planner/worker modes, tool dispatch, mode switching."""

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest

from hive.llm.agent import Agent, _parse_tools_line, _strip_tools_line
from hive.skills import SkillLibrary
from hive.tools.base import Tool
from hive.tools.registry import ToolRegistry


# -- Fixtures --


class FakeTool(Tool):
    tags = set()

    def __init__(self, name: str, description: tuple[str, str], schema: dict | None = None, **_):
        self.name = name
        self.description = description
        self._schema = schema or {"type": "object", "properties": {}}

    def input_schema(self) -> dict:
        return self._schema

    async def execute(self, params: dict[str, Any], **kw) -> dict[str, Any]:
        return {"ok": True}


@pytest.fixture()
def tools():
    return [
        FakeTool(
            "search", ("fuzzy search", "Search sequences by name."),
            schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search text"},
                    "tags": {"type": "string", "description": "Comma-separated tags"},
                },
                "required": ["query"],
            },
        ),
        FakeTool(
            "blast", ("similarity search", "Find similar sequences using BLAST."),
            schema={
                "type": "object",
                "properties": {"sequence": {"type": "string"}},
                "required": ["sequence"],
            },
        ),
    ]


@pytest.fixture()
def registry(tools):
    reg = ToolRegistry()
    for t in tools:
        reg.register(t)
    return reg


@pytest.fixture()
def skills(tmp_path):
    (tmp_path / "seq_search.md").write_text(
        "# Seq Search\n## When\nUser searches sequences.\n## Workflow\n1. search()\n"
    )
    (tmp_path / "blast_sim.md").write_text(
        "# BLAST\n## When\nUser wants similarity search.\n## Workflow\n1. blast()\n"
    )
    return SkillLibrary(tmp_path)


# -- Helpers --


def _text_response(content, usage=None):
    return {
        "choices": [{"message": {"content": content}}],
        "usage": usage or {"prompt_tokens": 50, "completion_tokens": 10},
    }


def _tool_call_response(calls, usage=None):
    """Build mock LLM response with tool calls.

    calls: list of (name, args_dict) or (name, args_dict, call_id).
    """
    tool_calls = []
    for i, c in enumerate(calls):
        name, args = c[0], c[1]
        cid = c[2] if len(c) > 2 else str(i + 1)
        tool_calls.append({
            "id": cid,
            "function": {"name": name, "arguments": json.dumps(args)},
        })
    return {
        "choices": [{"message": {"tool_calls": tool_calls}}],
        "usage": usage or {"prompt_tokens": 50, "completion_tokens": 10},
    }


def _mock_llm(responses):
    client = AsyncMock()
    client.chat = AsyncMock(side_effect=responses)
    return client


# -- Signatures --


class TestSignatures:
    def test_short_format(self, registry):
        sigs = registry.signatures()
        assert len(sigs) == len(registry.tools())
        for sig in sigs:
            assert " -> dict  # " in sig

    def test_typed_params(self, registry):
        sigs = registry.signatures()
        text = "\n".join(sigs)
        assert "search(query: str, tags: str | None = None)" in text
        assert "blast(sequence: str)" in text

    def test_detailed_includes_param_descriptions(self, registry):
        sigs = registry.signatures(detailed=True)
        text = "\n".join(sigs)
        assert "query: Search text" in text
        assert "tags: Comma-separated tags" in text


# -- Planner mode --


class TestPlannerMode:
    async def test_search_then_plan(self, registry, skills):
        """Planner: Search -> text plan -> switch to worker."""
        llm = _mock_llm([
            _tool_call_response([("Search", {"query": ""})]),
            _text_response("GOAL: find GFP plasmids"),
            _text_response("Here are the results."),
        ])
        agent = Agent(registry, skills)
        agent.prepare("find GFP", use_planner=True)
        result = await agent.run(llm, max_turns=10)
        assert result["type"] == "message"
        assert result["plan"] == "GOAL: find GFP plasmids"
        assert "results" in result["content"]
        assert llm.chat.call_count == 3

    async def test_read_injects_skill_into_system(self, registry, skills):
        """Read() injects skill content into planner system prompt."""
        llm = _mock_llm([
            _tool_call_response([("Read", {"name": "seq_search"})]),
            _text_response("GOAL: search for sequences"),
            _text_response("Done."),
        ])
        agent = Agent(registry, skills)
        agent.prepare("search stuff", use_planner=True)
        await agent.run(llm, max_turns=10)

        # Second call (planner turn 1): system prompt should have the skill
        turn1_msgs = llm.chat.call_args_list[1][0][0]
        system_msg = turn1_msgs[0]["content"]
        assert "## Domain Skills" in system_msg
        assert "seq_search" in system_msg

    async def test_conv_includes_tool_history(self, registry, skills):
        """After Read(), planner messages include assistant tool_calls + tool result."""
        llm = _mock_llm([
            _tool_call_response([("Read", {"name": "seq_search"})], usage={"prompt_tokens": 50, "completion_tokens": 10}),
            _text_response("GOAL: search"),
            _text_response("Done."),
        ])
        agent = Agent(registry, skills)
        agent.prepare("find stuff", use_planner=True)
        await agent.run(llm, max_turns=10)

        # Turn 1 messages: system + user + assistant(tool_calls) + tool(result)
        turn1_msgs = llm.chat.call_args_list[1][0][0]
        assert turn1_msgs[2]["role"] == "assistant"
        assert turn1_msgs[2]["tool_calls"][0]["function"]["name"] == "Read"
        assert turn1_msgs[3]["role"] == "tool"
        assert "Seq Search" in turn1_msgs[3]["content"]

    async def test_tool_choice_required_on_first_turn(self, registry, skills):
        """First planner turn forces tool_choice='required'."""
        llm = _mock_llm([
            _tool_call_response([("Search", {})]),
            _text_response("plan text"),
            _text_response("Done."),
        ])
        agent = Agent(registry, skills)
        agent.prepare("test", use_planner=True)
        await agent.run(llm, max_turns=10)

        turn0_kwargs = llm.chat.call_args_list[0][1]
        assert turn0_kwargs["tool_choice"] == "required"
        turn1_kwargs = llm.chat.call_args_list[1][1]
        assert turn1_kwargs.get("tool_choice") is None

    async def test_multi_read_in_one_turn(self, registry, skills):
        """Model reads two skills in a single turn."""
        llm = _mock_llm([
            _tool_call_response([
                ("Read", {"name": "seq_search"}),
                ("Read", {"name": "blast_sim"}),
            ]),
            _text_response("GOAL: combined search"),
            _text_response("Done."),
        ])
        agent = Agent(registry, skills)
        agent.prepare("search and blast", use_planner=True)
        await agent.run(llm, max_turns=10)

        # Turn 1: system + user + assistant + tool + tool = 5
        turn1_msgs = llm.chat.call_args_list[1][0][0]
        tool_msgs = [m for m in turn1_msgs if m["role"] == "tool"]
        assert len(tool_msgs) == 2

    async def test_read_missing_skill_lists_available(self, registry, skills):
        """Reading nonexistent skill returns available names."""
        llm = _mock_llm([
            _tool_call_response([("Read", {"name": "nonexistent"})]),
            _text_response("brief text"),
            _text_response("Done."),
        ])
        agent = Agent(registry, skills)
        agent.prepare("test", use_planner=True)
        await agent.run(llm, max_turns=10)

        # Tool result should list available skills
        turn1_msgs = llm.chat.call_args_list[1][0][0]
        tool_result = [m for m in turn1_msgs if m["role"] == "tool"][0]
        assert "seq_search" in tool_result["content"]
        assert "blast_sim" in tool_result["content"]

    async def test_planner_max_turns_switches_to_worker(self, registry, skills):
        """Planner hitting max turns switches to worker without plan."""
        llm = _mock_llm([
            # 4 planner turns of Search calls, then worker text
            _tool_call_response([("Search", {})]),
            _tool_call_response([("Search", {})]),
            _tool_call_response([("Search", {})]),
            _tool_call_response([("Search", {})]),
            _text_response("Worker response without plan."),
        ])
        agent = Agent(registry, skills)
        agent.prepare("test", use_planner=True)
        result = await agent.run(llm, max_turns=20)
        assert result["type"] == "message"
        assert "Worker response" in result["content"]


# -- Worker mode --


class TestWorkerMode:
    async def test_no_skills_starts_in_worker(self, registry):
        """No skills -> starts directly in worker mode."""
        llm = _mock_llm([_text_response("Hello.")])
        agent = Agent(registry, skills=None)
        agent.prepare("hello", use_planner=True)
        result = await agent.run(llm, max_turns=10)
        assert result["type"] == "message"
        assert llm.chat.call_count == 1

    async def test_use_planner_false_skips_planner(self, registry, skills):
        """use_planner=False starts in worker even with skills."""
        llm = _mock_llm([_text_response("Direct response.")])
        agent = Agent(registry, skills)
        agent.prepare("test", use_planner=False)
        result = await agent.run(llm, max_turns=10)
        assert result["type"] == "message"
        assert llm.chat.call_count == 1

    async def test_python_call(self, registry):
        """Worker Python tool call -> sandbox execution."""
        llm = _mock_llm([
            _tool_call_response([("Python", {"code": "x = 42"})]),
            _text_response("x is 42."),
        ])
        agent = Agent(registry, skills=None)
        agent.prepare("compute x", use_planner=False)
        result = await agent.run(llm, max_turns=10)
        assert result["type"] == "message"
        assert "42" in result["content"]

    async def test_worker_sees_plan_in_system_prompt(self, registry, skills):
        """After planner produces plan, worker sees it in system prompt."""
        llm = _mock_llm([
            _tool_call_response([("Search", {})]),
            _text_response("GOAL: search for GFP"),
            _text_response("Found GFP."),
        ])
        agent = Agent(registry, skills)
        agent.prepare("find GFP", use_planner=True)
        await agent.run(llm, max_turns=10)

        # Worker call (3rd): system prompt has plan
        worker_msgs = llm.chat.call_args_list[2][0][0]
        system_msg = [m for m in worker_msgs if m["role"] == "system"][0]
        assert "## Plan" in system_msg["content"]
        assert "GOAL: search for GFP" in system_msg["content"]


# -- Mode switching --


class TestModeSwitching:
    async def test_plan_command_switches_back(self, registry, skills):
        """Worker calling Plan() switches back to planner mode."""
        llm = _mock_llm([
            # Planner turn 0 (forced Search)
            _tool_call_response([("Search", {})]),
            # Planner turn 1: plan text
            _text_response("GOAL: initial plan"),
            # Worker turn 0: calls Plan()
            _tool_call_response([("Plan", {})]),
            # Planner turn 0 (forced Search again)
            _tool_call_response([("Search", {})]),
            # Planner turn 1: new plan
            _text_response("GOAL: revised plan"),
            # Worker: final response
            _text_response("All done."),
        ])
        agent = Agent(registry, skills)
        agent.prepare("complex task", use_planner=True)
        result = await agent.run(llm, max_turns=20)
        assert result["type"] == "message"
        assert result["plan"] == "GOAL: revised plan"

    async def test_planner_failure_falls_to_worker(self, registry, skills):
        """Planner LLM error -> switch to worker without plan."""
        llm = _mock_llm([
            Exception("LLM down"),
            _text_response("Recovered."),
        ])
        agent = Agent(registry, skills)
        agent.prepare("test", use_planner=True)
        result = await agent.run(llm, max_turns=10)
        assert result["type"] == "message"
        assert "Recovered" in result["content"]


# -- Parse/strip TOOLS line --


class TestParseToolsLine:
    def test_parses_tools(self):
        plan = "GOAL: search\nTOOLS: search, blast, profile\nDELIVER:\n1. search"
        assert _parse_tools_line(plan) == ["search", "blast", "profile"]

    def test_returns_none_when_missing(self):
        plan = "GOAL: search\nDELIVER:\n1. search"
        assert _parse_tools_line(plan) is None

    def test_empty_tools_returns_none(self):
        plan = "GOAL: search\nTOOLS: \nDELIVER:\n1. search"
        assert _parse_tools_line(plan) is None

    def test_strips_whitespace(self):
        plan = "TOOLS:  search ,  blast  "
        assert _parse_tools_line(plan) == ["search", "blast"]


class TestStripToolsLine:
    def test_removes_tools_line(self):
        plan = "GOAL: search\nTOOLS: search, blast\nDELIVER:\n1. search"
        result = _strip_tools_line(plan)
        assert "TOOLS:" not in result
        assert "GOAL: search" in result
        assert "DELIVER:" in result

    def test_no_tools_line_unchanged(self):
        plan = "GOAL: search\nDELIVER:\n1. search"
        assert _strip_tools_line(plan) == plan


# -- ToolRegistry.filtered --


class TestRegistryFiltered:
    def test_subset(self, registry):
        sub = registry.filtered(["search", "blast"])
        names = {t.name for t in sub.tools()}
        assert names == {"search", "blast"}

    def test_ignores_unknown(self, registry):
        sub = registry.filtered(["search", "nonexistent"])
        names = {t.name for t in sub.tools()}
        assert names == {"search"}

    def test_empty_names(self, registry):
        sub = registry.filtered([])
        assert len(sub.tools()) == 0


# -- Worker sees filtered tools --


class TestWorkerToolFiltering:
    async def test_tools_line_filters_worker(self, registry, skills):
        """Planner TOOLS: line causes worker to see filtered tools only."""
        llm = _mock_llm([
            _tool_call_response([("Search", {})]),
            _text_response("GOAL: find GFP\nTOOLS: search\nDELIVER:\n1. search"),
            _text_response("Done."),
        ])
        agent = Agent(registry, skills)
        agent.prepare("find GFP", use_planner=True)
        await agent.run(llm, max_turns=10)

        # Worker call (3rd): Python tool description should only show search
        worker_call = llm.chat.call_args_list[2]
        worker_tools = worker_call[1].get("tools") or worker_call[0][1]
        py_tool = [t for t in worker_tools if t["function"]["name"] == "Python"][0]
        desc = py_tool["function"]["description"]
        assert "search(" in desc
        # blast should NOT appear since it wasn't in TOOLS line
        assert "blast(" not in desc

    async def test_no_tools_line_uses_full_registry(self, registry, skills):
        """Without TOOLS line, worker sees all tools."""
        llm = _mock_llm([
            _tool_call_response([("Search", {})]),
            _text_response("GOAL: find GFP\nDELIVER:\n1. search"),
            _text_response("Done."),
        ])
        agent = Agent(registry, skills)
        agent.prepare("find GFP", use_planner=True)
        await agent.run(llm, max_turns=10)

        worker_call = llm.chat.call_args_list[2]
        worker_tools = worker_call[1].get("tools") or worker_call[0][1]
        py_tool = [t for t in worker_tools if t["function"]["name"] == "Python"][0]
        desc = py_tool["function"]["description"]
        assert "search(" in desc
        assert "blast(" in desc

    async def test_search_always_included(self, registry, skills):
        """Even if TOOLS doesn't list search, it's force-included."""
        llm = _mock_llm([
            _tool_call_response([("Search", {})]),
            _text_response("GOAL: blast\nTOOLS: blast\nDELIVER:\n1. blast"),
            _text_response("Done."),
        ])
        agent = Agent(registry, skills)
        agent.prepare("blast query", use_planner=True)
        await agent.run(llm, max_turns=10)

        worker_call = llm.chat.call_args_list[2]
        worker_tools = worker_call[1].get("tools") or worker_call[0][1]
        py_tool = [t for t in worker_tools if t["function"]["name"] == "Python"][0]
        desc = py_tool["function"]["description"]
        assert "search(" in desc
        assert "blast(" in desc

    async def test_tools_line_stripped_from_plan(self, registry, skills):
        """TOOLS line is removed from the plan injected into worker system prompt."""
        llm = _mock_llm([
            _tool_call_response([("Search", {})]),
            _text_response("GOAL: find GFP\nTOOLS: search\nDELIVER:\n1. search"),
            _text_response("Done."),
        ])
        agent = Agent(registry, skills)
        agent.prepare("find GFP", use_planner=True)
        await agent.run(llm, max_turns=10)

        worker_msgs = llm.chat.call_args_list[2][0][0]
        system_msg = [m for m in worker_msgs if m["role"] == "system"][0]
        assert "TOOLS:" not in system_msg["content"]
        assert "GOAL: find GFP" in system_msg["content"]
