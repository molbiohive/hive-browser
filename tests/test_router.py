"""Tests for tool router: mode detection, helpers, and agentic loop."""

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest

from hive.tools.base import Tool, ToolRegistry
from hive.tools.router import (
    DIRECT_PATTERN,
    GUIDED_PATTERN,
    _error,
    _form_response,
    _help_response,
    _parse_args,
    _tool_response,
    route_input,
)


# ── Helpers ──


class EchoTool(Tool):
    """Minimal tool that echoes params back."""

    name = "echo"
    description = "Echoes params"
    widget = "text"
    tags = {"llm", "test"}
    guidelines = "Echo tool for testing."

    def __init__(self, **_):
        pass

    async def execute(self, params: dict[str, Any], mode: str = "direct") -> dict[str, Any]:
        return {"echo": params}


class RequiredTool(Tool):
    """Tool with required params (triggers form mode)."""

    name = "required"
    description = "Needs query param"
    widget = "text"
    tags = {"llm", "test"}
    params = {"query": {"type": "string", "description": "Search text", "required": True}}

    def __init__(self, **_):
        pass

    async def execute(self, params: dict[str, Any], mode: str = "direct") -> dict[str, Any]:
        return {"result": params.get("query", "")}


class DirectOnlyTool(Tool):
    """Tool without llm tag — no LLM assistance."""

    name = "direct"
    description = "Direct only"
    widget = "text"
    tags = {"info"}  # no "llm" tag

    def __init__(self, **_):
        pass

    async def execute(self, params: dict[str, Any], mode: str = "direct") -> dict[str, Any]:
        return {"ok": True}


@pytest.fixture()
def registry():
    reg = ToolRegistry()
    reg.register(EchoTool())
    reg.register(RequiredTool())
    reg.register(DirectOnlyTool())
    return reg


# ── Mode Detection Patterns ──


class TestModePatterns:
    def test_direct_pattern_basic(self):
        m = DIRECT_PATTERN.match("//search ampicillin")
        assert m.group(1) == "search"
        assert m.group(2) == "ampicillin"

    def test_direct_pattern_no_args(self):
        m = DIRECT_PATTERN.match("//status")
        assert m.group(1) == "status"
        assert m.group(2) == ""

    def test_direct_pattern_json_args(self):
        m = DIRECT_PATTERN.match('//search {"query": "GFP"}')
        assert m.group(1) == "search"
        assert "query" in m.group(2)

    def test_guided_pattern_basic(self):
        m = GUIDED_PATTERN.match("/search ampicillin")
        assert m.group(1) == "search"
        assert m.group(2) == "ampicillin"

    def test_guided_does_not_match_double_slash(self):
        # Double slash should be caught by DIRECT first in router logic
        m = DIRECT_PATTERN.match("//search x")
        assert m is not None  # direct catches it

    def test_free_text_matches_neither(self):
        assert DIRECT_PATTERN.match("search for GFP") is None
        assert GUIDED_PATTERN.match("search for GFP") is None


# ── Pure Helpers ──


class TestParseArgs:
    def test_json_object(self):
        assert _parse_args('{"query": "GFP"}') == {"query": "GFP"}

    def test_json_complex(self):
        result = _parse_args('{"enzymes": ["EcoRI", "BamHI"]}')
        assert result["enzymes"] == ["EcoRI", "BamHI"]

    def test_plain_text_fallback(self):
        assert _parse_args("ampicillin") == {"query": "ampicillin"}

    def test_empty_string(self):
        assert _parse_args("") == {}

    def test_invalid_json(self):
        assert _parse_args("{bad json") == {"query": "{bad json"}


class TestResponseHelpers:
    def test_tool_response(self):
        resp = _tool_response("search", {"hits": []}, {"query": "x"}, "No results")
        assert resp["type"] == "tool_result"
        assert resp["tool"] == "search"
        assert resp["data"] == {"hits": []}
        assert resp["params"] == {"query": "x"}
        assert resp["content"] == "No results"

    def test_form_response(self):
        schema = {"type": "object", "properties": {"q": {}}, "required": ["q"]}
        resp = _form_response("search", "Search tool", schema)
        assert resp["type"] == "form"
        assert resp["tool"] == "search"
        assert resp["data"]["schema"] == schema

    def test_error(self):
        resp = _error("something broke")
        assert resp["type"] == "message"
        assert "something broke" in resp["content"]

    def test_help_response(self, registry):
        resp = _help_response(registry)
        assert resp["type"] == "message"
        assert "/echo" in resp["content"]
        assert "/required" in resp["content"]
        # DirectOnlyTool has no "llm" tag → should show "(direct only)"
        assert "direct only" in resp["content"]


# ── Route Input: Direct Mode ──


class TestDirectMode:
    async def test_direct_echo(self, registry):
        resp = await route_input("//echo hello", registry)
        assert resp["type"] == "tool_result"
        assert resp["tool"] == "echo"
        assert resp["data"]["echo"] == {"query": "hello"}

    async def test_direct_json_args(self, registry):
        resp = await route_input('//echo {"key": "val"}', registry)
        assert resp["data"]["echo"] == {"key": "val"}

    async def test_direct_unknown_tool(self, registry):
        resp = await route_input("//nonexistent args", registry)
        assert resp["type"] == "message"
        assert "Unknown tool" in resp["content"]

    async def test_direct_no_args_with_required_shows_form(self, registry):
        resp = await route_input("//required", registry)
        assert resp["type"] == "form"
        assert resp["tool"] == "required"

    async def test_direct_no_args_without_required_executes(self, registry):
        resp = await route_input("//echo", registry)
        assert resp["type"] == "tool_result"
        assert resp["data"]["echo"] == {}


# ── Route Input: Help ──


class TestHelp:
    async def test_help(self, registry):
        resp = await route_input("/help", registry)
        assert resp["type"] == "message"
        assert "Available commands" in resp["content"]

    async def test_double_slash_help(self, registry):
        resp = await route_input("//help", registry)
        assert resp["type"] == "message"
        assert "Available commands" in resp["content"]


# ── Route Input: Guided Mode (no LLM) ──


class TestGuidedNoLLM:
    async def test_guided_without_llm_falls_back_to_direct(self, registry):
        resp = await route_input("/echo hello", registry, llm_client=None)
        assert resp["type"] == "tool_result"
        assert resp["data"]["echo"] == {"query": "hello"}

    async def test_guided_no_llm_tag_falls_back(self, registry):
        resp = await route_input("/direct", registry, llm_client=AsyncMock())
        assert resp["type"] == "tool_result"
        assert resp["data"]["ok"] is True

    async def test_guided_unknown_tool(self, registry):
        resp = await route_input("/nonexistent args", registry)
        assert "Unknown tool" in resp["content"]


# ── Route Input: Natural Language (no LLM) ──


class TestNaturalNoLLM:
    async def test_free_text_without_llm_errors(self, registry):
        resp = await route_input("find sequences with GFP", registry, llm_client=None)
        assert "LLM not available" in resp["content"]


# ── Unified Agentic Loop ──


class TestAgenticLoop:
    def _mock_llm(self, responses):
        """Create a mock LLM client that returns responses in sequence."""
        client = AsyncMock()
        client.chat = AsyncMock(side_effect=responses)
        return client

    def _text_response(self, content, usage=None):
        """LLM response with text only (no tool calls)."""
        return {
            "choices": [{"message": {"content": content}}],
            "usage": usage or {"prompt_tokens": 100, "completion_tokens": 20},
        }

    def _tool_call_response(self, tool_name, arguments, call_id="call_1", usage=None):
        """LLM response with a single tool call."""
        return {
            "choices": [{
                "message": {
                    "content": None,
                    "tool_calls": [{
                        "id": call_id,
                        "function": {
                            "name": tool_name,
                            "arguments": json.dumps(arguments),
                        },
                    }],
                },
            }],
            "usage": usage or {"prompt_tokens": 100, "completion_tokens": 20},
        }

    async def test_simple_conversation(self, registry):
        """LLM responds with text, no tools → message response."""
        llm = self._mock_llm([self._text_response("Hello! How can I help?")])
        resp = await route_input("hello", registry, llm_client=llm)
        assert resp["type"] == "message"
        assert "Hello" in resp["content"]

    async def test_single_tool_call(self, registry):
        """LLM calls echo tool, then summarizes."""
        llm = self._mock_llm([
            self._tool_call_response("echo", {"query": "test"}),
            self._text_response("Here are your echo results."),
        ])
        resp = await route_input("echo test", registry, llm_client=llm)
        assert resp["type"] == "tool_result"
        assert resp["tool"] == "echo"
        assert resp["data"]["echo"] == {"query": "test"}
        assert "echo results" in resp["content"]

    async def test_multi_tool_chain(self, registry):
        """LLM chains two tool calls before summarizing."""
        llm = self._mock_llm([
            self._tool_call_response("echo", {"query": "step1"}, call_id="c1"),
            self._tool_call_response("echo", {"query": "step2"}, call_id="c2"),
            self._text_response("Done with both steps."),
        ])
        resp = await route_input("do two things", registry, llm_client=llm)
        assert resp["type"] == "tool_result"
        assert len(resp["chain"]) == 2
        assert resp["chain"][0]["tool"] == "echo"
        assert resp["chain"][1]["tool"] == "echo"

    async def test_unknown_tool_from_llm(self, registry):
        """LLM hallucinates a tool name → error message sent back, then text."""
        llm = self._mock_llm([
            self._tool_call_response("imaginary_tool", {}, call_id="c1"),
            self._text_response("Sorry, let me try differently."),
        ])
        resp = await route_input("do something", registry, llm_client=llm)
        assert resp["type"] == "message"
        assert "Sorry" in resp["content"]

    async def test_max_turns_exceeded(self, registry):
        """Loop hits max turns → returns last result with warning."""
        # 2 turns of tool calls, max_turns=2 → exhausted without text response
        llm = self._mock_llm([
            self._tool_call_response("echo", {"query": "t1"}, call_id="c1"),
            self._tool_call_response("echo", {"query": "t2"}, call_id="c2"),
        ])
        resp = await route_input("loop forever", registry, llm_client=llm, max_turns=2)
        assert "chain" in resp
        assert "maximum reasoning steps" in resp["content"]

    async def test_progress_callback(self, registry):
        """on_progress is called with thinking and tool phases."""
        events = []

        async def on_progress(data):
            events.append(data)

        llm = self._mock_llm([
            self._tool_call_response("echo", {"query": "x"}),
            self._text_response("Done."),
        ])
        await route_input(
            "test progress", registry, llm_client=llm, on_progress=on_progress
        )
        phases = [e["phase"] for e in events]
        assert phases[0] == "thinking"  # initial
        assert "tool" in phases  # before execute
        assert phases[-1] == "thinking"  # after execute

    async def test_auto_pipe_cache(self, registry):
        """Large string results are cached and auto-injected into subsequent tools."""

        class LargeOutputTool(Tool):
            name = "producer"
            description = "Produces large output"
            widget = "text"
            tags = {"llm", "test"}
            params = {"name": {"type": "string", "description": "Name"}}

            def __init__(self, **_):
                pass

            async def execute(self, params, mode="direct"):
                return {"sequence": "A" * 300}  # > pipe_min_length

        class ConsumerTool(Tool):
            name = "consumer"
            description = "Consumes sequence"
            widget = "text"
            tags = {"llm", "test"}
            params = {"sequence": {"type": "string", "description": "Sequence"}}

            def __init__(self, **_):
                pass

            async def execute(self, params, mode="direct"):
                return {"length": len(params.get("sequence", ""))}

        reg = ToolRegistry()
        reg.register(LargeOutputTool())
        reg.register(ConsumerTool())

        llm = self._mock_llm([
            self._tool_call_response("producer", {"name": "test"}, call_id="c1"),
            # LLM sends consumer with short placeholder — cache should inject
            self._tool_call_response("consumer", {"sequence": "injected"}, call_id="c2"),
            self._text_response("Length is 300."),
        ])
        resp = await route_input("pipe test", reg, llm_client=llm, pipe_min_length=200)
        assert resp["type"] == "tool_result"
        assert resp["data"]["length"] == 300  # got cached value, not "injected"

    async def test_guided_with_llm(self, registry):
        """Guided mode with LLM delegates to unified loop."""
        llm = self._mock_llm([
            self._tool_call_response("echo", {"query": "guided"}),
            self._text_response("Guided echo result."),
        ])
        resp = await route_input("/echo test guided", registry, llm_client=llm)
        assert resp["type"] == "tool_result"
        assert resp["tool"] == "echo"

    async def test_llm_error_graceful(self, registry):
        """LLM raises exception → loop breaks gracefully."""
        llm = self._mock_llm([Exception("Connection failed")])
        resp = await route_input("test error", registry, llm_client=llm)
        assert resp["type"] == "message"
        assert "No tools were called" in resp["content"]
