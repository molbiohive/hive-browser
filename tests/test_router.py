"""Tests for tool router: mode detection, helpers, and agentic loop."""

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest

from hive.tools import Tool, ToolRegistry
from hive.agent import (
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


class SearchStubTool(Tool):
    """Minimal search tool stub required by the agentic loop."""

    name = "search"
    description = ("fuzzy search", "Search sequences")
    tags = {"search"}

    def __init__(self, **_):
        pass

    def llm_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Query"}},
            "required": ["query"],
        }

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"results": [], "query": params.get("query", "")}


class EchoTool(Tool):
    """Minimal tool that echoes params back."""

    name = "echo"
    description = ("echo", "Echoes params")
    tags = {"test"}

    def __init__(self, **_):
        pass

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"echo": params}


class RequiredTool(Tool):
    """Tool with required params (triggers form mode)."""

    name = "required"
    description = ("required", "Needs query param")
    tags = {"test"}
    params = {"query": {"type": "string", "description": "Search text", "required": True}}

    def __init__(self, **_):
        pass

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"result": params.get("query", "")}


class TasksStubTool(Tool):
    """Minimal tasks tool stub required by the agentic loop."""

    name = "tasks"
    description = ("task list", "Manage tasks")
    tags = set()

    def __init__(self, **_):
        pass

    def llm_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "text": {"type": "string"},
            },
            "required": ["action"],
        }

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "action": params.get("action", "")}


class DirectOnlyTool(Tool):
    """Tool for direct-only testing."""

    name = "direct"
    description = ("direct", "Direct only")
    tags = {"info"}

    def __init__(self, **_):
        pass

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True}


@pytest.fixture()
def registry():
    reg = ToolRegistry()
    reg.register(SearchStubTool())
    reg.register(TasksStubTool())
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
        assert "/direct" in resp["content"]


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



# ── Route Input: Guided Mode (no LLM) ──


class TestGuidedNoLLM:
    async def test_guided_no_args_with_llm_uses_loop(self, registry):
        """Guided mode with LLM delegates to unified loop."""
        llm = AsyncMock()
        llm.chat = AsyncMock(
            return_value={
                "choices": [{"message": {"content": "Here's the direct tool."}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }
        )
        resp = await route_input("/direct", registry, llm_client=llm)
        assert resp["type"] == "message"

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
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": call_id,
                                "function": {
                                    "name": tool_name,
                                    "arguments": json.dumps(arguments),
                                },
                            }
                        ],
                    },
                }
            ],
            "usage": usage or {"prompt_tokens": 100, "completion_tokens": 20},
        }

    async def test_simple_conversation(self, registry):
        """LLM responds with text, no tools → message response."""
        llm = self._mock_llm([self._text_response("Hello! How can I help?")])
        resp = await route_input("hello", registry, llm_client=llm)
        assert resp["type"] == "message"
        assert "Hello" in resp["content"]

    async def test_single_tool_call(self, registry):
        """LLM calls tasks tool, then summarizes."""
        llm = self._mock_llm(
            [
                self._tool_call_response("tasks", {"action": "list"}),
                self._text_response("Here are your tasks."),
            ]
        )
        resp = await route_input("show tasks", registry, llm_client=llm)
        assert resp["type"] == "message"
        assert "tasks" in resp["content"].lower()

    async def test_multi_tool_chain(self, registry):
        """LLM chains two tasks calls before summarizing."""
        llm = self._mock_llm(
            [
                self._tool_call_response("tasks", {"action": "add", "text": "step1"}, call_id="c1"),
                self._tool_call_response("tasks", {"action": "add", "text": "step2"}, call_id="c2"),
                self._text_response("Done with both steps."),
            ]
        )
        resp = await route_input("add two tasks", registry, llm_client=llm)
        assert len(resp["chain"]) == 2
        assert resp["chain"][0]["tool"] == "tasks"
        assert resp["chain"][1]["tool"] == "tasks"

    async def test_unknown_tool_from_llm(self, registry):
        """LLM hallucinates a tool name → error message sent back, then text."""
        llm = self._mock_llm(
            [
                self._tool_call_response("imaginary_tool", {}, call_id="c1"),
                self._text_response("Sorry, let me try differently."),
            ]
        )
        resp = await route_input("do something", registry, llm_client=llm)
        assert resp["type"] == "message"
        assert "Sorry" in resp["content"]

    async def test_max_turns_exceeded(self, registry):
        """Loop hits max turns → returns last result with summary attempt."""
        llm = self._mock_llm(
            [
                self._tool_call_response("tasks", {"action": "add", "text": "t1"}, call_id="c1"),
                self._tool_call_response("tasks", {"action": "add", "text": "t2"}, call_id="c2"),
                # 3rd call: _final_summary (no tools) → text response
                self._text_response("Here is a summary of results."),
            ]
        )
        resp = await route_input("loop forever", registry, llm_client=llm, max_turns=2)
        assert "chain" in resp
        assert "summary of results" in resp["content"]

    async def test_progress_callback(self, registry):
        """on_progress is called with thinking phases."""
        events = []

        async def on_progress(data):
            events.append(data)

        llm = self._mock_llm(
            [
                self._tool_call_response("tasks", {"action": "list"}),
                self._text_response("Done."),
            ]
        )
        await route_input("test progress", registry, llm_client=llm, on_progress=on_progress)
        phases = [e["phase"] for e in events]
        assert phases[0] == "thinking"

    async def test_non_tasks_tool_rejected(self, registry):
        """Non-tasks tool called via function calling → error pointing to sandbox."""
        llm = self._mock_llm(
            [
                self._tool_call_response("search", {"query": "test"}),
                self._text_response("Let me use python instead."),
            ]
        )
        resp = await route_input("search test", registry, llm_client=llm)
        assert resp["type"] == "message"
        assert "python" in resp["content"].lower() or "Let me" in resp["content"]

    async def test_guided_with_llm(self, registry):
        """Guided mode with LLM delegates to unified loop."""
        llm = self._mock_llm(
            [
                self._text_response("Guided search result."),
            ]
        )
        resp = await route_input("/search test guided", registry, llm_client=llm)
        assert resp["type"] == "message"

    async def test_llm_error_graceful(self, registry):
        """LLM raises exception -> loop breaks gracefully with sanitized error."""
        llm = self._mock_llm([Exception("Connection failed")])
        resp = await route_input("test error", registry, llm_client=llm)
        assert resp["type"] == "message"
        assert "LLM error" in resp["content"]
        assert "Could not connect" in resp["content"]


# ── Error Sanitization ──


class TestErrorSanitization:
    def test_rate_limit(self):
        from hive.agent import _sanitize_llm_error

        assert _sanitize_llm_error("Rate limit exceeded: 429") == "Rate limit reached"

    def test_auth_error(self):
        from hive.agent import _sanitize_llm_error

        assert _sanitize_llm_error("AuthenticationError: invalid key") == "LLM auth failed"

    def test_timeout(self):
        from hive.agent import _sanitize_llm_error

        assert _sanitize_llm_error("Request timeout after 30s") == "LLM request timed out"

    def test_connection_error(self):
        from hive.agent import _sanitize_llm_error

        assert _sanitize_llm_error("ConnectionError: refused") == "Could not connect to LLM"

    def test_unknown_capped(self):
        from hive.agent import _sanitize_llm_error

        long_msg = "x" * 200
        result = _sanitize_llm_error(long_msg)
        assert len(result) <= 120



# ── Planner Integration ──


class TestPlannerIntegration:
    """Tests for planner integration in the router."""

    def _mock_llm(self, responses):
        client = AsyncMock()
        client.chat = AsyncMock(side_effect=responses)
        return client

    def _text_response(self, content, usage=None):
        return {
            "choices": [{"message": {"content": content}}],
            "usage": usage or {"prompt_tokens": 100, "completion_tokens": 20},
        }

    # ── Planner ON (default) ──

    async def test_planner_always_runs_agent_loop(self, registry):
        """Planner ON always runs agent loop -- no ANSWER shortcut."""
        from hive.llm.planner import Planner

        planner = Planner(tools=registry.tools())

        llm = self._mock_llm(
            [
                # Plan call
                self._text_response("respond conversationally"),
                # Agent loop
                self._text_response("Hello! How can I help?"),
            ]
        )
        resp = await route_input(
            "hello",
            registry,
            llm_client=llm,
            planner=planner,
            use_planner=True,
        )
        assert resp["type"] == "message"
        assert "Hello" in resp["content"]
        assert resp.get("plan") == "respond conversationally"
        assert llm.chat.call_count == 2  # plan + agent

    async def test_planner_on_injects_plan_text(self, registry):
        """Planner produces task description, agent sees plan in user message."""
        from hive.llm.planner import Planner

        planner = Planner(tools=registry.tools())

        llm = self._mock_llm(
            [
                self._text_response("Echo the input back."),
                self._text_response("Here is your echo."),
            ]
        )
        resp = await route_input(
            "echo test",
            registry,
            llm_client=llm,
            planner=planner,
            use_planner=True,
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

    async def test_planner_on_failure_falls_through(self, registry):
        """If planning call fails, agent continues without plan."""
        from hive.llm.planner import Planner

        planner = Planner(tools=registry.tools())

        llm = self._mock_llm(
            [
                Exception("LLM down"),
                self._text_response("Recovered."),
            ]
        )
        resp = await route_input(
            "test fallback",
            registry,
            llm_client=llm,
            planner=planner,
            use_planner=True,
        )
        assert resp["type"] == "message"
        assert "Recovered" in resp["content"]

    # ── Planner OFF ──

    async def test_planner_off_no_plan_call(self, registry):
        """Planner OFF: no plan() call, agent runs directly."""
        from hive.llm.planner import Planner

        planner = Planner(tools=registry.tools())
        planner.plan = AsyncMock()  # spy — should NOT be called

        llm = self._mock_llm([self._text_response("Done.")])
        resp = await route_input(
            "echo test",
            registry,
            llm_client=llm,
            planner=planner,
            use_planner=False,
        )
        assert resp["type"] == "message"
        planner.plan.assert_not_called()

    async def test_planner_off_agent_sees_user_input(self, registry):
        """Planner OFF: agent loop receives raw user input, not plan."""
        from hive.llm.planner import Planner

        planner = Planner(tools=registry.tools())

        llm = self._mock_llm([self._text_response("Hello.")])
        await route_input(
            "find GFP sequences",
            registry,
            llm_client=llm,
            planner=planner,
            use_planner=False,
        )
        # Only one LLM call (agent loop, no planning)
        assert llm.chat.call_count == 1
        agent_messages = llm.chat.call_args_list[0][0][0]
        user_msg = [m for m in agent_messages if m.get("role") == "user"][-1]
        assert user_msg["content"] == "find GFP sequences"



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
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": call_id,
                                "function": {
                                    "name": tool_name,
                                    "arguments": json.dumps(arguments),
                                },
                            }
                        ],
                    },
                }
            ],
            "usage": usage or {"prompt_tokens": 100, "completion_tokens": 20},
        }

    def _make_registry(self, *extra_tools):
        """Create a registry with tasks (required) + any extra tools."""
        reg = ToolRegistry()
        reg.register(TasksStubTool())
        for t in extra_tools:
            reg.register(t)
        return reg

    async def test_auto_cache_list_dict(self):
        """Search called from python produces workspace handles."""

        class SearchTool(Tool):
            name = "search"
            description = ("fuzzy search", "Search sequences")
            tags = {"search"}

            def __init__(self, **_):
                pass

            async def execute(self, params):
                return {
                    "results": [
                        {"sid": 1, "name": "GFP", "size_bp": 720},
                        {"sid": 2, "name": "RFP", "size_bp": 680},
                    ],
                    "query": "test",
                }

        reg = self._make_registry(SearchTool())
        llm = self._mock_llm(
            [
                self._tool_call_response(
                    "python",
                    {"code": 'r = search(query="test"); feedback = f"found {len(r[\"results\"])} results"'},
                    call_id="c1",
                ),
                self._text_response("Found 2 results."),
            ]
        )
        resp = await route_input("find test", reg, llm_client=llm)
        assert "Found 2 results" in resp["content"]
        # Verify python step appears in status (flat context rebuild)
        last_msgs = llm.chat.call_args_list[-1][0][0]
        status_msg = [
            m
            for m in last_msgs
            if isinstance(m, dict)
            and m.get("role") == "assistant"
            and "Done so far:" in m.get("content", "")
        ]
        assert status_msg, "Status summary should appear in rebuilt messages"
        assert "# ok: python" in status_msg[0]["content"]

    async def test_python_dispatched_to_sandbox(self):
        """python tool calls execute in sandbox with tools callable."""

        class SearchTool(Tool):
            name = "search"
            description = ("search", "Search")
            tags = {"search"}

            def __init__(self, **_):
                pass

            async def execute(self, params):
                return {
                    "results": [
                        {"sid": 1, "name": "GFP"},
                        {"sid": 2, "name": "RFP"},
                    ],
                }

        reg = self._make_registry(SearchTool())
        llm = self._mock_llm(
            [
                self._tool_call_response(
                    "python",
                    {"code": 'r = search(query="GFP"); feedback = str([x["sid"] for x in r["results"]])'},
                    call_id="c1",
                ),
                self._text_response("SIDs are 1 and 2."),
            ]
        )
        resp = await route_input("find GFP sids", reg, llm_client=llm)
        assert "SIDs are 1 and 2" in resp["content"]
        assert len(resp["chain"]) == 1
        assert resp["chain"][0]["tool"] == "python"

    async def test_python_schema_always_available(self):
        """python schema is available from turn 0 (always offered)."""
        reg = self._make_registry(SearchStubTool())
        llm = self._mock_llm([self._text_response("Done.")])
        await route_input("test", reg, llm_client=llm)

        first_call_tools = llm.chat.call_args_list[0][1].get("tools", [])
        tool_names_t0 = [t["function"]["name"] for t in first_call_tools]
        assert "python" in tool_names_t0
        assert "tasks" in tool_names_t0

    async def test_python_schema_always_present_despite_errors(self):
        """Python schema is never dropped, even after consecutive errors."""
        reg = self._make_registry(SearchStubTool())
        llm = self._mock_llm(
            [
                self._tool_call_response(
                    "python",
                    {"code": "feedback = undefined_var_1"},
                    call_id="c1",
                ),
                self._tool_call_response(
                    "python",
                    {"code": "feedback = undefined_var_2"},
                    call_id="c2",
                ),
                self._text_response("Could not process the data."),
            ]
        )
        await route_input("process data", reg, llm_client=llm, max_turns=10)

        last_call_tools = llm.chat.call_args_list[-1][1].get("tools", [])
        tool_names = [t["function"]["name"] for t in last_call_tools]
        assert "python" in tool_names
