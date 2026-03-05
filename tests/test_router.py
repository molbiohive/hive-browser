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

    async def test_direct_no_args_always_shows_form(self, registry):
        """All tools show a form when invoked with no args."""
        resp = await route_input("//echo", registry)
        assert resp["type"] == "form"
        assert resp["tool"] == "echo"


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

    async def test_guided_no_llm_tag_shows_form(self, registry):
        """Non-LLM tool with no args in guided mode shows a form."""
        resp = await route_input("/direct", registry, llm_client=AsyncMock())
        assert resp["type"] == "form"
        assert resp["tool"] == "direct"

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
            # LLM sends consumer with short placeholder -- cache should inject
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
        """LLM raises exception -> loop breaks gracefully."""
        llm = self._mock_llm([Exception("Connection failed")])
        resp = await route_input("test error", registry, llm_client=llm)
        assert resp["type"] == "message"
        assert "No tools were called" in resp["content"]


# ── Tool RAG Integration ──


class TestToolRAGIntegration:
    """Tests for two-mode RAG pipeline in the router.

    Mode 1 (planner ON):  plan() → RAG on plan → agent sees plan + selected tools
    Mode 2 (planner OFF): RAG on user input → agent sees user input + selected tools
    """

    def _mock_llm(self, responses):
        client = AsyncMock()
        client.chat = AsyncMock(side_effect=responses)
        return client

    def _text_response(self, content, usage=None):
        return {
            "choices": [{"message": {"content": content}}],
            "usage": usage or {"prompt_tokens": 100, "completion_tokens": 20},
        }

    def _tool_call_response(self, tool_name, arguments, call_id="call_1", usage=None):
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

    # ── Planner ON (default) ──

    async def test_planner_on_answer_skips_agent_loop(self, registry):
        """Planner ON + ANSWER prefix returns directly, no tool calls."""
        from hive.llm.tool_rag import ToolRAG

        rag = ToolRAG(tools=registry.llm_tools(), threshold=0.2, top_k=5)

        llm = self._mock_llm([
            self._text_response("ANSWER: GFP is Green Fluorescent Protein."),
        ])
        resp = await route_input(
            "What is GFP?", registry, llm_client=llm,
            tool_rag=rag, use_planner=True,
        )
        assert resp["type"] == "message"
        assert "Green Fluorescent Protein" in resp["content"]
        assert llm.chat.call_count == 1

    async def test_planner_on_action_narrows_tools(self, registry):
        """Planner ON + ACTION triggers RAG on plan, agent sees plan text."""
        from hive.llm.tool_rag import ToolRAG

        rag = ToolRAG(tools=registry.llm_tools(), threshold=0.2, top_k=5)

        llm = self._mock_llm([
            self._text_response("ACTION: Echo the input back."),
            self._text_response("Here is your echo."),
        ])
        resp = await route_input(
            "echo test", registry, llm_client=llm,
            tool_rag=rag, use_planner=True,
        )
        assert resp["type"] == "message"
        assert llm.chat.call_count == 2

        # Agent loop (second call) should see both plan and original user input
        agent_messages = llm.chat.call_args_list[1][0][0]
        user_msg = [m for m in agent_messages if m.get("role") == "user"][-1]
        assert "[Plan]" in user_msg["content"]
        assert "Echo the input back." in user_msg["content"]
        assert "[User request]" in user_msg["content"]
        assert "echo test" in user_msg["content"]

    async def test_planner_on_tokens_include_planning(self, registry):
        """Token counts include both planning and agent loop usage."""
        from hive.llm.tool_rag import ToolRAG

        rag = ToolRAG(tools=registry.llm_tools(), threshold=0.2, top_k=5)

        llm = self._mock_llm([
            self._text_response("ANSWER: Simple answer.",
                                usage={"prompt_tokens": 50, "completion_tokens": 10}),
        ])
        resp = await route_input(
            "hello", registry, llm_client=llm,
            tool_rag=rag, use_planner=True,
        )
        assert resp["tokens"]["in"] == 50
        assert resp["tokens"]["out"] == 10

    async def test_planner_on_failure_falls_through(self, registry):
        """If planning call fails, all tools are used (graceful degradation)."""
        from hive.llm.tool_rag import ToolRAG

        rag = ToolRAG(tools=registry.llm_tools(), threshold=0.2, top_k=5)

        llm = self._mock_llm([
            Exception("LLM down"),
            self._text_response("Recovered."),
        ])
        resp = await route_input(
            "test fallback", registry, llm_client=llm,
            tool_rag=rag, use_planner=True,
        )
        assert resp["type"] == "message"
        assert "Recovered" in resp["content"]

    # ── Planner OFF ──

    async def test_planner_off_rag_on_user_input(self, registry):
        """Planner OFF: no plan() call, RAG runs on user input directly."""
        from unittest.mock import AsyncMock as AM, patch

        from hive.llm.tool_rag import ToolRAG

        rag = ToolRAG(tools=registry.llm_tools(), threshold=0.2, top_k=5)
        rag.plan = AM()  # spy — should NOT be called
        original_select = rag.select
        select_args = []

        async def _spy_select(text):
            select_args.append(text)
            return await original_select(text)

        rag.select = _spy_select

        llm = self._mock_llm([self._text_response("Done.")])
        resp = await route_input(
            "echo test", registry, llm_client=llm,
            tool_rag=rag, use_planner=False,
        )
        assert resp["type"] == "message"
        # plan() was never called
        rag.plan.assert_not_called()
        # select() was called with user input (not plan text)
        assert len(select_args) == 1
        assert select_args[0] == "echo test"

    async def test_planner_off_agent_sees_user_input(self, registry):
        """Planner OFF: agent loop receives raw user input, not plan."""
        from hive.llm.tool_rag import ToolRAG

        rag = ToolRAG(tools=registry.llm_tools(), threshold=0.2, top_k=5)

        llm = self._mock_llm([self._text_response("Hello.")])
        await route_input(
            "find GFP sequences", registry, llm_client=llm,
            tool_rag=rag, use_planner=False,
        )
        # Only one LLM call (agent loop, no planning)
        assert llm.chat.call_count == 1
        agent_messages = llm.chat.call_args_list[0][0][0]
        user_msg = [m for m in agent_messages if m.get("role") == "user"][-1]
        assert user_msg["content"] == "find GFP sequences"

    async def test_planner_off_rag_failure_uses_all_tools(self, registry):
        """Planner OFF: if RAG select() fails, all tools are used."""
        from hive.llm.tool_rag import ToolRAG

        rag = ToolRAG(tools=registry.llm_tools(), threshold=0.2, top_k=5)
        rag.select = AsyncMock(side_effect=Exception("embedding down"))

        llm = self._mock_llm([self._text_response("Recovered.")])
        resp = await route_input(
            "test", registry, llm_client=llm,
            tool_rag=rag, use_planner=False,
        )
        assert resp["type"] == "message"
        assert "Recovered" in resp["content"]

    # ── Backward compatibility ──

    async def test_tool_rag_none_passes_all_tools(self, registry):
        """tool_rag=None (default) uses all tools, backward compatible."""
        llm = self._mock_llm([self._text_response("Hello!")])
        resp = await route_input("hello", registry, llm_client=llm, tool_rag=None)
        assert resp["type"] == "message"
        assert "Hello" in resp["content"]


# ── Sandbox Integration ──


class TestSandboxIntegration:
    """Tests for sandbox integration in the agentic loop."""

    def _mock_llm(self, responses):
        client = AsyncMock()
        client.chat = AsyncMock(side_effect=responses)
        return client

    def _text_response(self, content, usage=None):
        return {
            "choices": [{"message": {"content": content}}],
            "usage": usage or {"prompt_tokens": 100, "completion_tokens": 20},
        }

    def _tool_call_response(self, tool_name, arguments, call_id="call_1", usage=None):
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

    async def test_auto_cache_list_dict(self):
        """Tool results with list[dict] fields are auto-cached."""

        class SearchTool(Tool):
            name = "search"
            description = "Search sequences"
            widget = "table"
            tags = {"llm", "test"}

            def __init__(self, **_):
                pass

            async def execute(self, params, mode="direct"):
                return {
                    "results": [
                        {"sid": 1, "name": "GFP", "size_bp": 720},
                        {"sid": 2, "name": "RFP", "size_bp": 680},
                    ],
                    "query": "test",
                }

        reg = ToolRegistry()
        reg.register(SearchTool())

        llm = self._mock_llm([
            self._tool_call_response("search", {"query": "test"}, call_id="c1"),
            self._text_response("Found 2 results."),
        ])
        resp = await route_input("find test", reg, llm_client=llm)
        assert resp["type"] == "tool_result"
        assert resp["tool"] == "search"
        # Verify cache info appears in the tool message sent to LLM
        tool_msg = [m for m in llm.chat.call_args_list[-1][0][0]
                    if isinstance(m, dict) and m.get("role") == "tool"]
        assert any("Cached data" in m.get("content", "") for m in tool_msg)

    async def test_python_dispatched_to_sandbox(self):
        """python tool calls go to sandbox, not ToolRegistry."""

        class SearchTool(Tool):
            name = "search"
            description = "Search"
            widget = "table"
            tags = {"llm", "test"}

            def __init__(self, **_):
                pass

            async def execute(self, params, mode="direct"):
                return {
                    "results": [
                        {"sid": 1, "name": "GFP"},
                        {"sid": 2, "name": "RFP"},
                    ],
                }

        reg = ToolRegistry()
        reg.register(SearchTool())

        llm = self._mock_llm([
            self._tool_call_response("search", {"query": "GFP"}, call_id="c1"),
            self._tool_call_response(
                "python",
                {"code": 'result = [r["sid"] for r in r0]'},
                call_id="c2",
            ),
            self._text_response("SIDs are 1 and 2."),
        ])
        resp = await route_input("find GFP sids", reg, llm_client=llm)
        # Scalar sandbox keeps previous tool's widget visible
        assert resp["type"] == "tool_result"
        assert resp["tool"] == "search"
        assert "SIDs are 1 and 2" in resp["content"]
        assert len(resp["chain"]) == 2
        assert resp["chain"][0]["tool"] == "search"
        assert resp["chain"][1]["tool"] == "python"

    async def test_sandbox_scalar_keeps_previous_widget(self):
        """Scalar sandbox results keep the previous tool's widget visible."""

        class SearchTool(Tool):
            name = "search"
            description = "Search"
            widget = "table"
            tags = {"llm", "test"}

            def __init__(self, **_):
                pass

            async def execute(self, params, mode="direct"):
                return {
                    "results": [{"sid": 1, "topology": "circular"}],
                }

        reg = ToolRegistry()
        reg.register(SearchTool())

        llm = self._mock_llm([
            self._tool_call_response("search", {"query": "test"}, call_id="c1"),
            self._tool_call_response(
                "python",
                {"code": 'result = sum(1 for r in r0 if r["topology"] == "circular")'},
                call_id="c2",
            ),
            self._text_response("1 circular sequence."),
        ])
        resp = await route_input("count circular", reg, llm_client=llm)
        # Scalar sandbox keeps previous tool's widget
        assert resp["type"] == "tool_result"
        assert resp["tool"] == "search"
        assert "1 circular" in resp["content"]
        assert len(resp["chain"]) == 2
        assert resp["chain"][0]["tool"] == "search"
        assert resp["chain"][1]["tool"] == "python"
        assert resp["chain"][1]["summary"].startswith("Result: ")

    async def test_python_schema_injected_when_cache_nonempty(self):
        """python schema only appears after first tool caches data."""

        class SearchTool(Tool):
            name = "search"
            description = "Search"
            widget = "table"
            tags = {"llm", "test"}

            def __init__(self, **_):
                pass

            async def execute(self, params, mode="direct"):
                return {"results": [{"sid": 1}]}

        reg = ToolRegistry()
        reg.register(SearchTool())

        llm = self._mock_llm([
            self._tool_call_response("search", {"query": "x"}, call_id="c1"),
            self._text_response("Done."),
        ])
        await route_input("test", reg, llm_client=llm)

        # First LLM call (turn 0): no python schema (cache empty)
        first_call_tools = llm.chat.call_args_list[0][1].get("tools", [])
        tool_names_t0 = [t["function"]["name"] for t in first_call_tools]
        assert "python" not in tool_names_t0

        # Second LLM call (turn 1): python schema present (cache has data)
        second_call_tools = llm.chat.call_args_list[1][1].get("tools", [])
        tool_names_t1 = [t["function"]["name"] for t in second_call_tools]
        assert "python" in tool_names_t1

    async def test_cache_info_in_sandbox_response(self):
        """Sandbox response includes cache descriptions."""

        class SearchTool(Tool):
            name = "search"
            description = "Search"
            widget = "table"
            tags = {"llm", "test"}

            def __init__(self, **_):
                pass

            async def execute(self, params, mode="direct"):
                return {"results": [{"sid": 1, "name": "GFP"}]}

        reg = ToolRegistry()
        reg.register(SearchTool())

        llm = self._mock_llm([
            self._tool_call_response("search", {"query": "x"}, call_id="c1"),
            self._tool_call_response(
                "python", {"code": 'result = len(r0)'}, call_id="c2",
            ),
            self._text_response("1 result."),
        ])
        await route_input("count results", reg, llm_client=llm)

        # Check the tool message for the python call includes cache info
        last_call_msgs = llm.chat.call_args_list[-1][0][0]
        python_tool_msgs = [
            m for m in last_call_msgs
            if isinstance(m, dict) and m.get("role") == "tool"
            and "result = 1" in m.get("content", "")
        ]
        assert len(python_tool_msgs) == 1
        assert "Cached data:" in python_tool_msgs[0]["content"]

    async def test_sandbox_retries_exhaust_drops_python_schema(self):
        """After N consecutive sandbox errors, python schema is dropped."""

        class SearchTool(Tool):
            name = "search"
            description = "Search"
            widget = "table"
            tags = {"llm", "test"}

            def __init__(self, **_):
                pass

            async def execute(self, params, mode="direct"):
                return {"results": [{"sid": 1, "name": "GFP"}]}

        reg = ToolRegistry()
        reg.register(SearchTool())

        # Use code that triggers NameError in the sandbox (status: "error")
        llm = self._mock_llm([
            # Turn 0: search -> caches data
            self._tool_call_response("search", {"query": "x"}, call_id="c1"),
            # Turn 1: sandbox error #1
            self._tool_call_response(
                "python", {"code": "result = undefined_var_1"}, call_id="c2",
            ),
            # Turn 2: sandbox error #2
            self._tool_call_response(
                "python", {"code": "result = undefined_var_2"}, call_id="c3",
            ),
            # Turn 3: sandbox error #3
            self._tool_call_response(
                "python", {"code": "result = undefined_var_3"}, call_id="c4",
            ),
            # Turn 4: LLM gives up and responds with text
            self._text_response("Could not process the data."),
        ])
        resp = await route_input(
            "process data", reg, llm_client=llm,
            sandbox_max_retries=3, max_turns=10,
        )

        # Verify the 5th LLM call (after 3 errors) has no python schema
        # Calls: turn0(no python), turn1(+python), turn2(+python), turn3(+python),
        #   turn4(python dropped)
        assert llm.chat.call_count == 5
        # Turn 4 (index 4): python schema should be gone
        last_call_tools = llm.chat.call_args_list[4][1].get("tools", [])
        tool_names = [t["function"]["name"] for t in last_call_tools]
        assert "python" not in tool_names

        # But turn 3 (index 3) still had python (only 2 errors at that point)
        third_retry_tools = llm.chat.call_args_list[3][1].get("tools", [])
        tool_names_3 = [t["function"]["name"] for t in third_retry_tools]
        assert "python" in tool_names_3
