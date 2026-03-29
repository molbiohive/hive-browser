"""Tests for Planner: tool signatures and planning call."""

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest

from hive.llm.planner import Planner
from hive.skills import SkillLibrary
from hive.tools.base import Tool, ToolRegistry

# -- Fixtures --


class FakeTool(Tool):
    """Minimal tool for testing."""

    tags = set()

    def __init__(self, name: str, description: tuple[str, str], schema: dict | None = None, **_):
        self.name = name
        self.description = description
        self._schema = schema or {"type": "object", "properties": {}}

    def llm_schema(self) -> dict:
        return self._schema

    async def execute(self, params: dict[str, Any], **kw) -> dict[str, Any]:
        return {"ok": True}


@pytest.fixture()
def tools():
    return [
        FakeTool(
            "search",
            ("fuzzy search", "Search sequences by name, features, and metadata."),
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
            "blast",
            ("similarity search", "Find similar sequences using BLAST+ alignment."),
            schema={
                "type": "object",
                "properties": {"sequence": {"type": "string"}},
                "required": ["sequence"],
            },
        ),
        FakeTool("translate", ("DNA to protein", "Translate a DNA or RNA sequence to protein.")),
        FakeTool("extract", ("extract subsequence", "Extract a subsequence by feature or region.")),
        FakeTool(
            "profile",
            ("sequence detail", "Show full details of a specific sequence."),
            schema={
                "type": "object",
                "properties": {"sid": {"type": "integer"}},
                "required": ["sid"],
            },
        ),
        FakeTool("digest", ("restriction digest", "Find restriction enzyme cut sites and fragment sizes.")),
        FakeTool("gc", ("GC content", "Calculate GC content and nucleotide composition.")),
        FakeTool("revcomp", ("reverse complement", "Get the reverse complement of a DNA sequence.")),
        FakeTool("transcribe", ("DNA to mRNA", "Transcribe DNA to mRNA.")),
        FakeTool("align", ("sequence alignment", "Align multiple sequences using MAFFT.")),
        FakeTool("parts", ("part lookup", "Look up a part by PID, or list parts on a sequence.")),
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


@pytest.fixture()
def planner(registry, skills):
    return Planner(registry=registry, skills=skills)


# -- Signatures --


class TestSignatures:
    def test_short_format(self, registry):
        sigs = registry.signatures()
        assert len(sigs) == len(registry.tools())
        for sig in sigs:
            assert " -- " in sig

    def test_typed_params(self, registry):
        sigs = registry.signatures()
        text = "\n".join(sigs)
        assert "search(query:string, tags:string?)" in text
        assert "blast(sequence:string)" in text
        assert "profile(sid:integer)" in text

    def test_short_description(self, registry):
        sigs = registry.signatures()
        text = "\n".join(sigs)
        assert "fuzzy search" in text
        assert "similarity search" in text

    def test_detailed_includes_param_descriptions(self, registry):
        sigs = registry.signatures(detailed=True)
        text = "\n".join(sigs)
        assert "query: Search text" in text
        assert "tags: Comma-separated tags" in text


# -- Planning --


def _mock_llm(content):
    """Build a mock LLM that returns a text response."""
    client = AsyncMock()
    client.chat = AsyncMock(
        return_value={
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 10},
        }
    )
    return client


def _mock_llm_multiturn(responses):
    """Build a mock LLM that returns tool_calls then text across turns."""
    client = AsyncMock()
    client.chat = AsyncMock(side_effect=[
        {
            "choices": [{"message": resp}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 10},
        }
        for resp in responses
    ])
    return client


class TestPlan:
    async def test_returns_plan_text_and_usage(self, planner):
        llm = _mock_llm("Search the database for GFP sequences.")
        plan_text, usage = await planner.prepare("find GFP").run(llm)
        assert "GFP" in plan_text
        assert usage["in"] == 50
        assert usage["out"] == 10

    async def test_conversational_plan(self, planner):
        llm = _mock_llm("respond conversationally")
        plan_text, _ = await planner.prepare("hello").run(llm)
        assert "conversationally" in plan_text

    async def test_plan_passes_history(self, planner):
        llm = _mock_llm("Follow up on the previous search.")
        history = [{"role": "user", "content": "prev"}, {"role": "assistant", "content": "ok"}]
        await planner.prepare("follow up", history=history).run(llm)
        call_args = llm.chat.call_args[0][0]
        # system + 2 history + user = 4 messages
        assert len(call_args) == 4

    async def test_catalog_has_typed_signatures(self, planner):
        llm = _mock_llm("plan text")
        await planner.prepare("test").run(llm)
        messages = llm.chat.call_args[0][0]
        system_msg = messages[0]["content"]
        assert "search(query:string, tags:string?)" in system_msg
        assert "query: Search text" in system_msg

    async def test_brief_format_in_system_prompt(self, planner):
        llm = _mock_llm("plan text")
        await planner.prepare("test").run(llm)
        system_msg = llm.chat.call_args[0][0][0]["content"]
        for keyword in ("GOAL:", "DELIVER:", "STOP:"):
            assert keyword in system_msg

    async def test_skills_section_in_system_prompt(self, planner):
        llm = _mock_llm("plan text")
        await planner.prepare("test").run(llm)
        system_msg = llm.chat.call_args[0][0][0]["content"]
        assert "search()" in system_msg
        assert "read(name)" in system_msg


# -- Skill Integration --


class TestSkillIntegration:
    async def test_read_then_brief(self, planner):
        """Two-turn flow: read -> text brief."""
        llm = _mock_llm_multiturn([
            # Turn 1: LLM calls read(name)
            {"tool_calls": [{"id": "1", "function": {"name": "read", "arguments": json.dumps({"name": "seq_search"})}}]},
            # Turn 2: LLM produces text brief
            {"content": "GOAL: find GFP plasmids"},
        ])
        plan_text, usage = await planner.prepare("find GFP").run(llm, max_turns=4)
        assert "GOAL" in plan_text
        assert usage["in"] == 100  # 50 * 2 turns

        # Verify skill content was injected into system prompt on turn 2
        last_messages = llm.chat.call_args[0][0]
        system_msg = last_messages[0]["content"]
        assert "## Domain Skills" in system_msg
        assert "seq_search" in system_msg

    async def test_conv_includes_tool_history(self, planner):
        """After read(), messages include assistant tool_calls + tool result."""
        llm = _mock_llm_multiturn([
            {"tool_calls": [{"id": "tc1", "function": {"name": "read", "arguments": json.dumps({"name": "seq_search"})}}]},
            {"content": "GOAL: search"},
        ])
        await planner.prepare("find stuff").run(llm, max_turns=4)

        # Inspect turn 2 messages
        turn2_msgs = llm.chat.call_args[0][0]
        # system + user + assistant(tool_calls) + tool(result) = 4
        assert len(turn2_msgs) == 4
        assert turn2_msgs[2]["role"] == "assistant"
        assert turn2_msgs[2]["tool_calls"][0]["id"] == "tc1"
        assert turn2_msgs[3]["role"] == "tool"
        assert turn2_msgs[3]["tool_call_id"] == "tc1"
        assert "Seq Search" in turn2_msgs[3]["content"]

    async def test_search_and_read_tools_offered(self, planner):
        """Planner offers search and read tools."""
        llm = _mock_llm("plan text")
        await planner.prepare("test").run(llm)
        call_kwargs = llm.chat.call_args[1]
        tools = call_kwargs.get("tools")
        assert tools is not None
        names = {t["function"]["name"] for t in tools}
        assert names == {"search", "read"}

    async def test_read_missing_skill_includes_available(self, planner):
        """Reading nonexistent skill returns available names in tool result."""
        llm = _mock_llm_multiturn([
            {"tool_calls": [{"id": "1", "function": {"name": "read", "arguments": json.dumps({"name": "nonexistent"})}}]},
            {"content": "brief text"},
        ])
        plan_text, _ = await planner.prepare("test").run(llm, max_turns=3)
        assert plan_text == "brief text"
        system_msg = llm.chat.call_args[0][0][0]["content"]
        assert "## Domain Skills" not in system_msg

        # Tool result should list available skills
        tool_result_msg = llm.chat.call_args[0][0][3]
        assert tool_result_msg["role"] == "tool"
        assert "seq_search" in tool_result_msg["content"]
        assert "blast_sim" in tool_result_msg["content"]

    async def test_tool_choice_required_on_first_turn(self, planner):
        """First turn forces tool_choice='required', second turn does not."""
        llm = _mock_llm_multiturn([
            {"tool_calls": [{"id": "1", "function": {"name": "read", "arguments": json.dumps({"name": "seq_search"})}}]},
            {"content": "GOAL: search"},
        ])
        await planner.prepare("find stuff").run(llm, max_turns=4)

        # Two calls: turn 0 (forced) + turn 1 (text)
        assert llm.chat.call_count == 2
        # Turn 0: tool_choice="required"
        turn0_kwargs = llm.chat.call_args_list[0][1]
        assert turn0_kwargs["tool_choice"] == "required"
        # Turn 1: tool_choice=None (not forced)
        turn1_kwargs = llm.chat.call_args_list[1][1]
        assert turn1_kwargs.get("tool_choice") is None

    async def test_multi_read_in_one_turn(self, planner):
        """Model reads two skills in a single turn."""
        llm = _mock_llm_multiturn([
            {"tool_calls": [
                {"id": "1", "function": {"name": "read", "arguments": json.dumps({"name": "seq_search"})}},
                {"id": "2", "function": {"name": "read", "arguments": json.dumps({"name": "blast_sim"})}},
            ]},
            {"content": "GOAL: combined search"},
        ])
        plan_text, _ = await planner.prepare("search and blast").run(llm, max_turns=4)
        assert "GOAL" in plan_text

        # Turn 2 should have: system + user + assistant + tool + tool = 5
        turn2_msgs = llm.chat.call_args[0][0]
        assert len(turn2_msgs) == 5
        tool_msgs = [m for m in turn2_msgs if m["role"] == "tool"]
        assert len(tool_msgs) == 2
