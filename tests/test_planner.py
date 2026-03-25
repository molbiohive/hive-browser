"""Tests for Planner: catalog building and planning call."""

from typing import Any
from unittest.mock import AsyncMock

import pytest

from hive.llm.planner import Planner
from hive.llm.prompts import build_tool_catalog
from hive.tools.base import Tool


# ── Fixtures ──


class FakeTool(Tool):
    """Minimal tool for testing."""

    tags = set()

    def __init__(self, name: str, description: str, **_):
        self.name = name
        self.description = description

    async def execute(self, params: dict[str, Any], **kw) -> dict[str, Any]:
        return {"ok": True}


@pytest.fixture()
def tools():
    return [
        FakeTool("search", "Search sequences by name, features, and metadata."),
        FakeTool("blast", "Find similar sequences using BLAST+ alignment."),
        FakeTool("translate", "Translate a DNA or RNA sequence to protein."),
        FakeTool("extract", "Extract a subsequence by feature or region."),
        FakeTool("profile", "Show full details of a specific sequence."),
        FakeTool("digest", "Find restriction enzyme cut sites and fragment sizes."),
        FakeTool("gc", "Calculate GC content and nucleotide composition."),
        FakeTool("revcomp", "Get the reverse complement of a DNA sequence."),
        FakeTool("transcribe", "Transcribe DNA to mRNA."),
        FakeTool("align", "Align multiple sequences using MAFFT."),
        FakeTool("parts", "Look up a part by PID, or list parts on a sequence."),
    ]


@pytest.fixture()
def planner(tools):
    return Planner(tools=tools)


# ── Catalog ──


class TestCatalog:
    def test_catalog_format(self, tools):
        catalog = build_tool_catalog(tools)
        lines = catalog.strip().split("\n")
        assert len(lines) == len(tools)
        for line in lines:
            assert line.startswith("- ")
            assert ": " in line

    def test_catalog_uses_description(self, tools):
        """Catalog should use short description, not guidelines."""
        catalog = build_tool_catalog(tools)
        assert "Search sequences by name" in catalog
        assert "BLAST+" in catalog


# ── Planning ──


class TestPlan:
    def _mock_llm(self, content):
        client = AsyncMock()
        client.chat = AsyncMock(return_value={
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 10},
        })
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
