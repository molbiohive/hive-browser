"""Tests for tool system: base class, factory, import validation, prompts."""

import textwrap
from typing import Any

from zerg.config import Settings
from zerg.tools.base import Tool, ToolRegistry, _auto_summarize, _params_to_schema
from zerg.tools.factory import ToolFactory, _is_forbidden, _validate_imports

# ── Helpers ──


class DummyTool(Tool):
    name = "dummy"
    description = "A test tool"
    widget = "text"
    tags = {"llm", "test"}
    guidelines = "Use for testing."

    def __init__(self, **_):
        pass

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"result": "ok", "query": params.get("query", "")}


class ParamsTool(Tool):
    """Tool using declarative params instead of Pydantic."""
    name = "paramtool"
    description = "Declarative params tool"
    params = {
        "query": {"type": "string", "description": "Search text", "required": True},
        "limit": {"type": "integer", "description": "Max results", "default": 10},
        "mode": {"type": "string", "description": "Mode", "enum": ["fast", "precise"]},
    }

    def __init__(self, **_):
        pass

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"data": params}


# ── Tool Base Class ──


class TestToolMetadata:
    def test_metadata_fields(self):
        t = DummyTool()
        meta = t.metadata()
        assert meta["name"] == "dummy"
        assert meta["description"] == "A test tool"
        assert meta["widget"] == "text"
        assert sorted(meta["tags"]) == ["llm", "test"]

    def test_schema(self):
        t = DummyTool()
        schema = t.schema()
        assert schema["name"] == "dummy"
        assert schema["description"] == "A test tool"
        assert "properties" in schema["parameters"]

    def test_group_returns_first_non_system_tag(self):
        t = DummyTool()
        assert t.group() == "test"

    def test_group_returns_none_for_system_only(self):
        t = DummyTool()
        t.tags = {"llm"}
        assert t.group() is None

    def test_format_result_default_error(self):
        t = DummyTool()
        assert t.format_result({"error": "fail"}) == "Error: fail"

    def test_format_result_default_empty(self):
        t = DummyTool()
        assert t.format_result({"result": "ok"}) == ""


class TestParamsToSchema:
    def test_basic(self):
        schema = _params_to_schema({
            "query": {"type": "string", "description": "Search", "required": True},
        })
        assert schema["type"] == "object"
        assert "query" in schema["properties"]
        assert schema["properties"]["query"]["type"] == "string"
        assert schema["required"] == ["query"]

    def test_optional_with_default(self):
        schema = _params_to_schema({
            "limit": {"type": "integer", "default": 10},
        })
        assert schema["properties"]["limit"]["default"] == 10
        assert "required" not in schema

    def test_enum(self):
        schema = _params_to_schema({
            "mode": {"type": "string", "enum": ["fast", "precise"]},
        })
        assert schema["properties"]["mode"]["enum"] == ["fast", "precise"]

    def test_declarative_tool_schema(self):
        t = ParamsTool()
        schema = t.input_schema()
        assert schema["required"] == ["query"]
        assert "limit" in schema["properties"]
        assert schema["properties"]["limit"]["default"] == 10


class TestAutoSummarize:
    def test_scalars(self):
        result = _auto_summarize({"count": 42, "name": "GFP", "active": True})
        assert "42" in result
        assert "GFP" in result
        assert "true" in result.lower()

    def test_list_count_and_sample(self):
        items = [{"name": f"seq{i}", "size": i * 100} for i in range(50)]
        result = _auto_summarize({"results": items})
        assert "results_count" in result
        assert "50" in result
        assert "results_sample" in result

    def test_long_string_truncated(self):
        result = _auto_summarize({"dna": "A" * 500})
        assert "..." in result
        assert len(result) < 500

    def test_nested_dict_shallow(self):
        result = _auto_summarize({"file": {"path": "/data/test.dna", "size": 1024}})
        assert "/data/test.dna" in result
        assert "1024" in result

    def test_max_chars_cap(self):
        huge = {f"key{i}": "x" * 100 for i in range(100)}
        result = _auto_summarize(huge, max_chars=500)
        assert len(result) <= 520  # 500 + "..."


# ── Tool Registry ──


class TestToolRegistry:
    def test_register_and_get(self):
        reg = ToolRegistry()
        t = DummyTool()
        reg.register(t)
        assert reg.get("dummy") is t
        assert reg.get("nonexistent") is None

    def test_all(self):
        reg = ToolRegistry()
        reg.register(DummyTool())
        assert len(reg.all()) == 1

    def test_llm_tools(self):
        reg = ToolRegistry()
        t1 = DummyTool()
        t1.tags = {"llm", "search"}
        t2 = DummyTool()
        t2.name = "info"
        t2.tags = {"info"}  # no llm tag
        reg.register(t1)
        reg.register(t2)
        llm = reg.llm_tools()
        assert len(llm) == 1
        assert llm[0].name == "dummy"

    def test_visible_tools_excludes_hidden(self):
        reg = ToolRegistry()
        t1 = DummyTool()
        t2 = DummyTool()
        t2.name = "secret"
        t2.tags = {"hidden"}
        reg.register(t1)
        reg.register(t2)
        visible = reg.visible_tools()
        assert len(visible) == 1
        assert visible[0].name == "dummy"

    def test_metadata(self):
        reg = ToolRegistry()
        reg.register(DummyTool())
        meta = reg.metadata()
        assert len(meta) == 1
        assert meta[0]["name"] == "dummy"


# ── Import Validation ──


class TestImportValidation:
    def test_sdk_allowed(self):
        assert _validate_imports("from zerg.sdk import Tool") == []
        assert _validate_imports("from zerg.sdk.db import ToolDB") == []
        assert _validate_imports("import zerg.sdk.widgets") == []

    def test_internal_forbidden(self):
        assert _validate_imports("from zerg.db.models import Sequence") == ["zerg.db.models"]
        assert _validate_imports("from zerg.tools.base import Tool") == ["zerg.tools.base"]
        assert _validate_imports("import zerg.config") == ["zerg.config"]
        assert _validate_imports("from zerg.llm.client import LLMClient") == ["zerg.llm.client"]
        assert _validate_imports("from zerg.server.app import create_app") == ["zerg.server.app"]

    def test_stdlib_and_thirdparty_allowed(self):
        assert _validate_imports("import os\nimport json\nimport pathlib") == []
        assert _validate_imports("import numpy") == []
        assert _validate_imports("from collections import defaultdict") == []

    def test_syntax_error_rejected(self):
        violations = _validate_imports("def broken(")
        assert violations == ["<syntax error>"]

    def test_multiple_violations(self):
        code = "from zerg.db import session\nfrom zerg.config import Settings"
        violations = _validate_imports(code)
        assert len(violations) == 2

    def test_is_forbidden_helper(self):
        assert _is_forbidden("zerg.db") is True
        assert _is_forbidden("zerg.db.models") is True
        assert _is_forbidden("zerg.sdk") is False
        assert _is_forbidden("zerg.sdk.db") is False
        assert _is_forbidden("os") is False


# ── ToolFactory — Internal Discovery ──


class TestToolFactoryInternal:
    def test_discovers_all_internal_tools(self):
        config = Settings()
        registry = ToolFactory.discover(config, llm_client=None)
        names = {t.name for t in registry.all()}
        assert names == {
            "search", "blast", "profile", "status", "model",
            "extract", "translate", "transcribe", "digest",
            "gc", "revcomp", "features", "primers",
        }

    def test_tool_attributes(self):
        config = Settings()
        registry = ToolFactory.discover(config, llm_client=None)
        search = registry.get("search")
        assert search is not None
        assert search.widget == "table"
        assert "llm" in search.tags
        assert search.group() == "search"

    def test_llm_tools_subset(self):
        config = Settings()
        registry = ToolFactory.discover(config, llm_client=None)
        llm_names = {t.name for t in registry.llm_tools()}
        assert llm_names == {
            "search", "blast", "profile",
            "extract", "translate", "transcribe", "digest",
            "gc", "revcomp", "features", "primers",
        }

    def test_visible_tools_all_visible(self):
        """No internal tools are hidden."""
        config = Settings()
        registry = ToolFactory.discover(config, llm_client=None)
        assert len(registry.visible_tools()) == 13


# ── ToolFactory — External Discovery ──


class TestToolFactoryExternal:
    def test_load_valid_external_tool(self, tmp_path):
        tool_code = textwrap.dedent("""\
            from zerg.sdk import Tool

            class GCTool(Tool):
                name = "gc"
                description = "Calculate GC content"
                widget = "text"
                tags = {"llm", "analysis"}
                params = {
                    "name": {"type": "string", "description": "Sequence name", "required": True},
                }

                async def execute(self, params):
                    return {"gc_content": 42.5}
        """)
        (tmp_path / "gc_content.py").write_text(tool_code)

        config = Settings()
        config.tools.directory = str(tmp_path)
        registry = ToolFactory.discover(config, llm_client=None)

        gc = registry.get("gc")
        assert gc is not None
        assert gc.description == "Calculate GC content"
        assert gc.db is not None  # ToolDB injected
        assert gc.group() == "analysis"

    def test_reject_forbidden_imports(self, tmp_path):
        bad_code = textwrap.dedent("""\
            from zerg.db.models import Sequence
            from zerg.sdk import Tool

            class BadTool(Tool):
                name = "bad"
                description = "Forbidden imports"
                async def execute(self, params):
                    return {}
        """)
        (tmp_path / "bad_tool.py").write_text(bad_code)

        config = Settings()
        config.tools.directory = str(tmp_path)
        registry = ToolFactory.discover(config, llm_client=None)

        assert registry.get("bad") is None  # rejected

    def test_skip_underscore_files(self, tmp_path):
        (tmp_path / "_helper.py").write_text("x = 1")
        (tmp_path / "__init__.py").write_text("")

        config = Settings()
        config.tools.directory = str(tmp_path)
        registry = ToolFactory.discover(config, llm_client=None)

        # Only internal tools, no external loaded
        internal_names = {
            "search", "blast", "profile", "status", "model",
            "extract", "translate", "transcribe", "digest",
            "gc", "revcomp", "features", "primers",
        }
        assert all(t.name in internal_names for t in registry.all())

    def test_external_overrides_internal(self, tmp_path):
        override_code = textwrap.dedent("""\
            from zerg.sdk import Tool

            class CustomSearch(Tool):
                name = "search"
                description = "Custom search override"

                async def execute(self, params):
                    return {"custom": True}
        """)
        (tmp_path / "custom_search.py").write_text(override_code)

        config = Settings()
        config.tools.directory = str(tmp_path)
        registry = ToolFactory.discover(config, llm_client=None)

        search = registry.get("search")
        assert search.description == "Custom search override"

    def test_missing_directory_no_error(self):
        config = Settings()
        config.tools.directory = "/nonexistent/path"
        registry = ToolFactory.discover(config, llm_client=None)
        assert len(registry.all()) == 13  # just internal tools


# ── Prompts ──


class TestPrompts:
    def test_selection_prompt_groups(self):
        from zerg.llm.prompts import build_selection_prompt

        config = Settings()
        registry = ToolFactory.discover(config)
        prompt = build_selection_prompt(registry)

        assert "## search" in prompt
        assert "## info" in prompt
        assert "## analysis" in prompt
        assert "- search:" in prompt
        assert "- blast:" in prompt
        assert "- profile:" in prompt
        assert "- extract:" in prompt
        assert "- translate:" in prompt
        # Non-LLM tools should not appear
        assert "- status:" not in prompt
        assert "- model:" not in prompt

    def test_execution_prompt_includes_tool_name(self):
        from zerg.llm.prompts import build_execution_prompt

        config = Settings()
        registry = ToolFactory.discover(config)
        tool = registry.get("blast")
        prompt = build_execution_prompt(tool)

        assert "`blast`" in prompt
        assert tool.guidelines in prompt

    def test_summary_prompt_includes_data(self):
        from zerg.llm.prompts import build_summary_prompt

        prompt = build_summary_prompt("Found 50 results for GFP.")
        assert "Found 50 results for GFP." in prompt
        assert "Summarize" in prompt

    def test_tool_schema_format(self):
        from zerg.llm.prompts import build_tool_schema

        config = Settings()
        registry = ToolFactory.discover(config)
        tool = registry.get("search")
        schema = build_tool_schema(tool)

        assert len(schema) == 1
        assert schema[0]["type"] == "function"
        assert schema[0]["function"]["name"] == "search"
        assert "properties" in schema[0]["function"]["parameters"]
