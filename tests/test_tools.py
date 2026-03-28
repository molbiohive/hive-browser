"""Tests for tool system: base class, factory, prompts."""

from typing import Any

from hive.config import Settings
from hive.tools.base import Tool, ToolRegistry, _params_to_schema
from hive.tools.factory import ToolFactory

# -- Helpers --


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


# -- Tool Base Class --


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


# -- Tool Registry --


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


# -- ToolFactory -- Internal Discovery --


class TestToolFactoryInternal:
    def test_discovers_all_internal_tools(self):
        config = Settings()
        registry = ToolFactory.discover(config)
        names = {t.name for t in registry.tools()}
        assert {"search", "blast", "profile", "digest", "extract"} <= names
        assert len(names) >= 10

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
        assert {"search", "blast", "profile", "digest"} <= all_names


# -- Prompts --


class TestPrompts:
    def test_system_prompt_content(self):
        from hive.llm.worker import system_prompt

        prompt = system_prompt()

        assert "Hive Browser" in prompt
        assert "fabricate" in prompt
        assert "## Rules" in prompt
        assert "sid:N" in prompt
        assert "pid:N" in prompt
