"""Tests for tool system: base class, factory, import validation, prompts."""

import textwrap
from typing import Any

from hive.config import Settings
from hive.tools.base import Tool, ToolRegistry, _params_to_schema
from hive.tools.factory import ToolFactory, _is_forbidden, _validate_imports

# ── Helpers ──


class DummyTool(Tool):
    name = "dummy"
    description = ("test", "A test tool")
    tags = {"test"}

    def __init__(self, **_):
        pass

    async def execute(self, params: dict[str, Any], mode: str = "direct") -> dict[str, Any]:
        return {"result": "ok", "query": params.get("query", "")}


class ParamsTool(Tool):
    """Tool using declarative params instead of Pydantic."""

    name = "paramtool"
    description = ("params test", "Declarative params tool")
    params = {
        "query": {"type": "string", "description": "Search text", "required": True},
        "limit": {"type": "integer", "description": "Max results", "default": 10},
        "mode": {"type": "string", "description": "Mode", "enum": ["fast", "precise"]},
    }

    def __init__(self, **_):
        pass

    async def execute(self, params: dict[str, Any], mode: str = "direct") -> dict[str, Any]:
        return {"data": params}


# ── Tool Base Class ──


class TestToolMetadata:
    def test_metadata_fields(self):
        t = DummyTool()
        meta = t.metadata()
        assert meta["name"] == "dummy"
        assert meta["description"] == "A test tool"  # long_desc used in metadata
        assert "widget" not in meta
        assert sorted(meta["tags"]) == ["test"]

    def test_schema(self):
        t = DummyTool()
        schema = t.schema()
        assert schema["name"] == "dummy"
        assert schema["description"] == "A test tool"
        assert "properties" in schema["parameters"]

    def test_group_returns_first_tag(self):
        t = DummyTool()
        assert t.group() == "test"

    def test_format_result_default_error(self):
        t = DummyTool()
        assert t.format_result({"error": "fail"}) == "Error: fail"

    def test_format_result_default_empty(self):
        t = DummyTool()
        assert t.format_result({"result": "ok"}) == ""


class TestParamsToSchema:
    def test_basic(self):
        schema = _params_to_schema(
            {
                "query": {"type": "string", "description": "Search", "required": True},
            }
        )
        assert schema["type"] == "object"
        assert "query" in schema["properties"]
        assert schema["properties"]["query"]["type"] == "string"
        assert schema["required"] == ["query"]

    def test_enum(self):
        schema = _params_to_schema(
            {
                "mode": {"type": "string", "enum": ["fast", "precise"]},
            }
        )
        assert schema["properties"]["mode"]["enum"] == ["fast", "precise"]

    def test_declarative_tool_schema(self):
        t = ParamsTool()
        schema = t.input_schema()
        assert schema["required"] == ["query"]
        assert "limit" in schema["properties"]
        assert schema["properties"]["limit"]["default"] == 10


# ── Tool Registry ──


class TestToolRegistry:
    def test_register_and_get(self):
        reg = ToolRegistry()
        t = DummyTool()
        reg.register(t)
        assert reg.get("dummy") is t
        assert reg.get("nonexistent") is None

    def test_tools_returns_all(self):
        reg = ToolRegistry()
        t1 = DummyTool()
        t1.tags = {"search"}
        t2 = DummyTool()
        t2.name = "info"
        t2.tags = {"info"}
        reg.register(t1)
        reg.register(t2)
        tools = reg.tools()
        assert len(tools) == 2

    def test_metadata(self):
        reg = ToolRegistry()
        reg.register(DummyTool())
        meta = reg.metadata()
        assert len(meta) == 1
        assert meta[0]["name"] == "dummy"


# ── Import Validation ──


class TestImportValidation:
    def test_sdk_allowed(self):
        assert _validate_imports("from hive.sdk import Tool") == []
        assert _validate_imports("from hive.sdk.db import ToolDB") == []
        assert _validate_imports("import hive.sdk.widgets") == []

    def test_internal_forbidden(self):
        assert _validate_imports("from hive.db.models import Sequence") == ["hive.db.models"]
        assert _validate_imports("from hive.tools.base import Tool") == ["hive.tools.base"]
        assert _validate_imports("import hive.config") == ["hive.config"]
        assert _validate_imports("from hive.llm.client import LLMClient") == ["hive.llm.client"]
        assert _validate_imports("from hive.server.app import create_app") == ["hive.server.app"]

    def test_stdlib_and_thirdparty_allowed(self):
        assert _validate_imports("import os\nimport json\nimport pathlib") == []
        assert _validate_imports("import numpy") == []
        assert _validate_imports("from collections import defaultdict") == []

    def test_syntax_error_rejected(self):
        violations = _validate_imports("def broken(")
        assert violations == ["<syntax error>"]

    def test_multiple_violations(self):
        code = "from hive.db import session\nfrom hive.config import Settings"
        violations = _validate_imports(code)
        assert len(violations) == 2

    def test_is_forbidden_helper(self):
        assert _is_forbidden("hive.db") is True
        assert _is_forbidden("hive.db.models") is True
        assert _is_forbidden("hive.sdk") is False
        assert _is_forbidden("hive.sdk.db") is False
        assert _is_forbidden("os") is False


# ── ToolFactory — Internal Discovery ──


class TestToolFactoryInternal:
    def test_discovers_all_internal_tools(self):
        config = Settings()
        registry = ToolFactory.discover(config)
        names = {t.name for t in registry.tools()}
        # Verify core tools are present (not exhaustive — new tools can be added)
        assert {"search", "blast", "profile", "digest", "extract"} <= names
        assert len(names) >= 10  # reasonable minimum

    def test_tool_attributes(self):
        config = Settings()
        registry = ToolFactory.discover(config)
        search = registry.get("search")
        assert search is not None
        assert search.group() == "search"

    def test_all_tools_registered(self):
        config = Settings()
        registry = ToolFactory.discover(config)
        all_names = {t.name for t in registry.tools()}
        # Core tools must be registered
        assert {"search", "blast", "profile", "digest"} <= all_names


# ── ToolFactory — External Discovery ──


class TestToolFactoryExternal:
    def test_load_valid_external_tool(self, tmp_path):
        tool_code = textwrap.dedent("""\
            from hive.sdk import Tool

            class GCTool(Tool):
                name = "gc"
                description = "Calculate GC content"
                tags = {"analysis"}
                params = {
                    "name": {"type": "string", "description": "Sequence name", "required": True},
                }

                async def execute(self, params, mode="direct"):
                    return {"gc_content": 42.5}
        """)
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        (tools_dir / "gc_content.py").write_text(tool_code)

        config = Settings(data_root=str(tmp_path))
        registry = ToolFactory.discover(config)

        gc = registry.get("gc")
        assert gc is not None
        assert gc.description == "Calculate GC content"
        assert gc.db is not None  # ToolDB injected
        assert gc.group() == "analysis"

    def test_reject_forbidden_imports(self, tmp_path):
        bad_code = textwrap.dedent("""\
            from hive.db.models import Sequence
            from hive.sdk import Tool

            class BadTool(Tool):
                name = "bad"
                description = "Forbidden imports"
                async def execute(self, params, mode="direct"):
                    return {}
        """)
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        (tools_dir / "bad_tool.py").write_text(bad_code)

        config = Settings(data_root=str(tmp_path))
        registry = ToolFactory.discover(config)

        assert registry.get("bad") is None  # rejected

    def test_skip_underscore_files(self, tmp_path):
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        (tools_dir / "_helper.py").write_text("x = 1")
        (tools_dir / "__init__.py").write_text("")

        config = Settings(data_root=str(tmp_path))
        registry = ToolFactory.discover(config)

        # No underscore files loaded as external tools
        names = {t.name for t in registry.tools()}
        assert "_helper" not in names
        assert "__init__" not in names

    def test_external_overrides_internal(self, tmp_path):
        override_code = textwrap.dedent("""\
            from hive.sdk import Tool

            class CustomSearch(Tool):
                name = "search"
                description = "Custom search override"

                async def execute(self, params, mode="direct"):
                    return {"custom": True}
        """)
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        (tools_dir / "custom_search.py").write_text(override_code)

        config = Settings(data_root=str(tmp_path))
        registry = ToolFactory.discover(config)

        search = registry.get("search")
        assert search.description == "Custom search override"

    def test_missing_directory_no_error(self):
        config = Settings(data_root="/nonexistent")
        registry = ToolFactory.discover(config)
        assert len(registry.tools()) >= 10  # just internal tools


# ── Prompts ──


class TestPrompts:
    def test_system_prompt_content(self):
        from hive.llm.prompts import build_system_prompt

        prompt = build_system_prompt()

        assert "Hive Browser" in prompt
        assert "fabricate" in prompt
        assert "## Rules" in prompt
        assert "sid:N" in prompt
        assert "pid:N" in prompt
