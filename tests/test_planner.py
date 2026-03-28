"""Tests for Planner: tool signatures and planning call."""

from typing import Any
from unittest.mock import AsyncMock

import pytest

from hive.llm.planner import Planner
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
def planner(registry):
    return Planner(registry=registry)


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


class TestPlan:
    def _mock_llm(self, content):
        client = AsyncMock()
        client.chat = AsyncMock(
            return_value={
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 10},
            }
        )
        return client

    async def test_returns_plan_text_and_usage(self, planner):
        llm = self._mock_llm("Search the database for GFP sequences.")
        plan_text, usage = await planner.plan("find GFP", llm)
        assert "GFP" in plan_text
        assert usage["in"] == 50
        assert usage["out"] == 10

    async def test_conversational_plan(self, planner):
        llm = self._mock_llm("respond conversationally")
        plan_text, _ = await planner.plan("hello", llm)
        assert "conversationally" in plan_text

    async def test_plan_passes_history(self, planner):
        llm = self._mock_llm("Follow up on the previous search.")
        history = [{"role": "user", "content": "prev"}, {"role": "assistant", "content": "ok"}]
        await planner.plan("follow up", llm, history=history)
        call_args = llm.chat.call_args[0][0]
        # system + 2 history + user = 4 messages
        assert len(call_args) == 4

    async def test_catalog_has_typed_signatures(self, planner):
        """Planner catalog uses detailed signatures from registry."""
        llm = self._mock_llm("plan text")
        await planner.plan("test", llm)
        messages = llm.chat.call_args[0][0]
        system_msg = messages[0]["content"]
        assert "search(query:string, tags:string?)" in system_msg
        assert "query: Search text" in system_msg
