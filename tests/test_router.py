"""Tests for tool router: mode detection, helpers, and agentic loop."""

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest

from hive.skills import SkillLibrary
from hive.tools import Tool, ToolRegistry
from hive.router import (
    DIRECT_PATTERN,
    GUIDED_PATTERN,
    _error,
    _form_response,
    _help_response,
    _parse_args,
    _tool_response,
    route_input,
)

# -- Helpers --


class SearchStubTool(Tool):
    """Minimal search tool stub required by the agentic loop."""

    name = "search"
    description = ("fuzzy search", "Search sequences")
    tags = {"search"}

    def __init__(self, **_):
        pass

    def input_schema(self) -> dict:
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
    reg.register(EchoTool())
    reg.register(RequiredTool())
    reg.register(DirectOnlyTool())
    return reg


# -- Mode Detection Patterns --


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



# -- Pure Helpers --


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


# -- Route Input: Direct Mode --


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


# -- Route Input: Help --


class TestHelp:
    async def test_help(self, registry):
        resp = await route_input("/help", registry)
        assert resp["type"] == "message"
        assert "Available commands" in resp["content"]



# -- Route Input: Guided Mode (no LLM) --


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


# -- Route Input: Natural Language (no LLM) --


class TestNaturalNoLLM:
    async def test_free_text_without_llm_errors(self, registry):
        resp = await route_input("find sequences with GFP", registry, llm_client=None)
        assert "LLM not available" in resp["content"]


# -- Unified Agentic Loop --


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
        """LLM responds with text, no tools -> message response."""
        llm = self._mock_llm([self._text_response("Hello! How can I help?")])
        resp = await route_input("hello", registry, llm_client=llm)
        assert resp["type"] == "message"
        assert "Hello" in resp["content"]

    async def test_single_tool_call(self, registry):
        """LLM calls Python tool, then summarizes."""
        llm = self._mock_llm(
            [
                self._tool_call_response("Python", {"code": "x = 1 + 1"}),
                self._text_response("x is 2."),
            ]
        )
        resp = await route_input("compute x", registry, llm_client=llm)
        assert resp["type"] == "message"

    async def test_multi_tool_chain(self, registry):
        """LLM chains two Python calls before summarizing."""
        llm = self._mock_llm(
            [
                self._tool_call_response("Python", {"code": "x = 1"}, call_id="c1"),
                self._tool_call_response("Python", {"code": "y = 2"}, call_id="c2"),
                self._text_response("Done with both steps."),
            ]
        )
        resp = await route_input("compute values", registry, llm_client=llm)
        assert len(resp["chain"]) == 2
        assert resp["chain"][0]["tool"] == "python"
        assert resp["chain"][1]["tool"] == "python"

    async def test_unknown_tool_from_llm(self, registry):
        """LLM hallucinates a tool name -> error message sent back, then text."""
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
        """Loop hits max turns -> returns last result with summary attempt."""
        llm = self._mock_llm(
            [
                self._tool_call_response("Python", {"code": "x = 1"}, call_id="c1"),
                self._tool_call_response("Python", {"code": "y = 2"}, call_id="c2"),
                # 3rd call: _final_summary (no tools) -> text response
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
                self._tool_call_response("Python", {"code": "x = 1"}),
                self._text_response("Done."),
            ]
        )
        await route_input("test progress", registry, llm_client=llm, on_progress=on_progress)
        phases = [e["phase"] for e in events]
        assert phases[0] == "thinking"

    async def test_non_python_tool_rejected(self, registry):
        """Non-python tool called via function calling -> error pointing to sandbox."""
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


# -- Error Sanitization --


class TestErrorSanitization:
    def test_rate_limit(self):
        from hive.llm.agent import Agent

        assert Agent._sanitize_error("Rate limit exceeded: 429") == "Rate limit reached"

    def test_auth_error(self):
        from hive.llm.agent import Agent

        assert Agent._sanitize_error("AuthenticationError: invalid key") == "LLM auth failed"

    def test_timeout(self):
        from hive.llm.agent import Agent

        assert Agent._sanitize_error("Request timeout after 30s") == "LLM request timed out"

    def test_connection_error(self):
        from hive.llm.agent import Agent

        assert Agent._sanitize_error("ConnectionError: refused") == "Could not connect to LLM"

    def test_unknown_capped(self):
        from hive.llm.agent import Agent

        long_msg = "x" * 200
        result = Agent._sanitize_error(long_msg)
        assert len(result) <= 120



# -- Planner Integration --


class TestPlannerIntegration:
    """Tests for unified agent planner/worker mode switching via router."""

    def _mock_llm(self, responses):
        client = AsyncMock()
        client.chat = AsyncMock(side_effect=responses)
        return client

    def _text_response(self, content, usage=None):
        return {
            "choices": [{"message": {"content": content}}],
            "usage": usage or {"prompt_tokens": 100, "completion_tokens": 20},
        }

    def _tool_call_response(self, name, args, call_id="1", usage=None):
        import json as _json
        return {
            "choices": [{"message": {"tool_calls": [
                {"id": call_id, "function": {"name": name, "arguments": _json.dumps(args)}},
            ]}}],
            "usage": usage or {"prompt_tokens": 50, "completion_tokens": 10},
        }

    def _skills(self, tmp_path):
        (tmp_path / "basic.md").write_text("# Basic\n## When\nAlways.\n## Workflow\n1. search()\n")
        return SkillLibrary(tmp_path)

    # -- Planner ON (default) --

    async def test_planner_on_produces_plan_then_worker(self, registry, tmp_path):
        """With skills + planner ON: planner Search -> plan text -> worker response."""
        skills = self._skills(tmp_path)

        llm = self._mock_llm([
            # Turn 0 (planner, forced): Search tool call
            self._tool_call_response("Search", {"query": ""}),
            # Turn 1 (planner): plan text -> switch to worker
            self._text_response("respond conversationally"),
            # Turn 2 (worker): final response
            self._text_response("Hello! How can I help?"),
        ])
        resp = await route_input(
            "hello", registry, llm_client=llm,
            skills=skills, use_planner=True,
        )
        assert resp["type"] == "message"
        assert "Hello" in resp["content"]
        assert resp.get("plan") == "respond conversationally"
        assert llm.chat.call_count == 3  # search + plan + worker

    async def test_planner_on_injects_plan_text(self, registry, tmp_path):
        """Plan text appears in worker system prompt."""
        skills = self._skills(tmp_path)

        llm = self._mock_llm([
            self._tool_call_response("Search", {"query": ""}),
            self._text_response("Echo the input back."),
            self._text_response("Here is your echo."),
        ])
        resp = await route_input(
            "echo test", registry, llm_client=llm,
            skills=skills, use_planner=True,
        )
        assert resp["type"] == "message"

        # Worker call (third): plan in system prompt, user input separate
        worker_messages = llm.chat.call_args_list[2][0][0]
        system_msg = [m for m in worker_messages if m.get("role") == "system"][0]
        assert "## Plan" in system_msg["content"]
        assert "Echo the input back." in system_msg["content"]
        user_msg = [m for m in worker_messages if m.get("role") == "user"][-1]
        assert "echo test" in user_msg["content"]

    async def test_planner_on_failure_falls_through(self, registry, tmp_path):
        """If planner LLM call fails, agent switches to worker without plan."""
        skills = self._skills(tmp_path)

        llm = self._mock_llm([
            Exception("LLM down"),       # planner fails -> switch to worker
            self._text_response("Recovered."),   # worker succeeds
        ])
        resp = await route_input(
            "test fallback", registry, llm_client=llm,
            skills=skills, use_planner=True,
        )
        assert resp["type"] == "message"
        assert "Recovered" in resp["content"]

    # -- Planner OFF --

    async def test_planner_off_no_plan_call(self, registry, tmp_path):
        """use_planner=False: starts in worker mode, no planner calls."""
        skills = self._skills(tmp_path)

        llm = self._mock_llm([self._text_response("Done.")])
        resp = await route_input(
            "echo test", registry, llm_client=llm,
            skills=skills, use_planner=False,
        )
        assert resp["type"] == "message"
        assert llm.chat.call_count == 1

    async def test_planner_off_agent_sees_user_input(self, registry, tmp_path):
        """use_planner=False: worker receives raw user input, no plan."""
        skills = self._skills(tmp_path)

        llm = self._mock_llm([self._text_response("Hello.")])
        await route_input(
            "find GFP sequences", registry, llm_client=llm,
            skills=skills, use_planner=False,
        )
        assert llm.chat.call_count == 1
        agent_messages = llm.chat.call_args_list[0][0][0]
        user_msg = [m for m in agent_messages if m.get("role") == "user"][-1]
        assert user_msg["content"] == "find GFP sequences"



# -- Sandbox Integration --


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
        """Create a registry with any extra tools."""
        reg = ToolRegistry()
        for t in extra_tools:
            reg.register(t)
        return reg

    async def test_auto_cache_list_dict(self):
        """Search called from python -> variables persist in workspace."""

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
                    "Python",
                    {"code": 'r = search(query="test")\ncount = len(r["results"])'},
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
                    "Python",
                    {"code": 'r = search(query="GFP")\nsids = [x["sid"] for x in r["results"]]'},
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
        assert "Python" in tool_names_t0

    async def test_python_schema_always_present_despite_errors(self):
        """Python schema is never dropped, even after consecutive errors."""
        reg = self._make_registry(SearchStubTool())
        llm = self._mock_llm(
            [
                self._tool_call_response(
                    "Python",
                    {"code": "x = undefined_var_1"},
                    call_id="c1",
                ),
                self._tool_call_response(
                    "Python",
                    {"code": "x = undefined_var_2"},
                    call_id="c2",
                ),
                self._text_response("Could not process the data."),
            ]
        )
        await route_input("process data", reg, llm_client=llm, max_turns=10)

        last_call_tools = llm.chat.call_args_list[-1][1].get("tools", [])
        tool_names = [t["function"]["name"] for t in last_call_tools]
        assert "Python" in tool_names
