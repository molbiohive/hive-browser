"""Tests for sandbox: Workspace, safe_exec, and SandboxRunner."""

from hive.sandbox.exec import safe_exec
from hive.sandbox.runner import SandboxRunner
from hive.sandbox.workspace import Workspace

# -- Workspace --


class TestWorkspace:
    def test_describe_user_vars_list(self):
        ws = Workspace()
        ws.update_vars({"results": [{"sid": 1, "name": "GFP", "size": 720}]})
        desc = ws.describe()
        assert "# results" in desc
        assert "1 rows" in desc
        assert "sid" in desc
        assert "results[0]" in desc

    def test_describe_user_vars_string(self):
        ws = Workspace()
        ws.update_vars({"sequence_data": "ATGC" * 100})
        desc = ws.describe()
        assert "str(400)" in desc

    def test_describe_user_vars_list_int(self):
        ws = Workspace()
        ws.update_vars({"fragments": [4521, 2100, 800]})
        desc = ws.describe()
        assert "list(3)" in desc

    def test_describe_user_vars_dict(self):
        ws = Workspace()
        ws.update_vars({"gel_data": {"lanes": [], "gelType": "agarose", "stain": "ethidium"}})
        desc = ws.describe()
        assert "dict" in desc
        assert "gelType" in desc

    def test_describe_multiple_vars(self):
        ws = Workspace()
        ws.update_vars({"a": [{"x": 1}], "b": "ATGC" * 100})
        text = ws.describe()
        assert "# a" in text
        assert "# b" in text

    def test_describe_empty(self):
        ws = Workspace()
        assert ws.describe() == "Empty."

    def test_report_entries_shown(self):
        ws = Workspace()
        desc = ws.describe(report={"overview": [{"a": 1}]})
        assert 'report["overview"]' in desc

    def test_available_commands_shown(self):
        ws = Workspace()
        desc = ws.describe(tool_signatures=["search(query)", "desc(var) -- inspect"])
        assert "# search(query)" in desc
        assert "# desc(var)" in desc

    def test_desc_results_shown_and_cleared(self):
        ws = Workspace()
        ws.add_desc_result("p0", "3 rows -- {sid: int, name: str}")
        desc = ws.describe()
        assert "desc(p0):" in desc
        assert "3 rows" in desc
        # Second call should have no desc results
        desc2 = ws.describe()
        assert "desc(" not in desc2

    def test_history_ok_with_produced(self):
        ws = Workspace()
        ws.add_step("python", "done", produced="results (56 rows)")
        h = ws.history()
        assert "# ok: python -> results (56 rows)" in h

    def test_history_error_with_hint(self):
        ws = Workspace()
        ws.add_step("python", "err", error="KeyError: 'gc'", hint="keys: {sid, name}")
        h = ws.history()
        assert "# x: python KeyError: 'gc' -- keys: {sid, name}" in h

    def test_reset_loop(self):
        ws = Workspace()
        ws.update_vars({"x": 1})
        ws.add_step("python", "done")
        ws.reset_loop()
        assert ws.user_vars == {}
        assert ws.steps == []

    def test_add_desc_result(self):
        ws = Workspace()
        ws.add_desc_result("myvar", "detail text")
        assert len(ws._desc_results) == 1
        assert ws._desc_results[0] == ("myvar", "detail text")


# -- safe_exec --


class TestSafeExec:
    def test_filter_list(self):
        data = [{"name": "GFP", "size": 720}, {"name": "RFP", "size": 680}]
        result = safe_exec(
            'feedback = [r for r in data if r["size"] > 700]',
            {"data": data},
        )
        assert result["status"] == "ok"
        assert len(result["feedback"]) == 1
        assert result["feedback"][0]["name"] == "GFP"

    def test_aggregation(self):
        data = [{"v": 10}, {"v": 20}, {"v": 30}]
        result = safe_exec('feedback = sum(r["v"] for r in data)', {"data": data})
        assert result["status"] == "ok"
        assert result["feedback"] == 60

    def test_sorted_result(self):
        data = [{"n": "C"}, {"n": "A"}, {"n": "B"}]
        result = safe_exec(
            'feedback = sorted(data, key=lambda r: r["n"])',
            {"data": data},
        )
        assert result["status"] == "ok"
        assert [r["n"] for r in result["feedback"]] == ["A", "B", "C"]

    def test_comprehension(self):
        data = [{"id": 1}, {"id": 2}, {"id": 3}]
        result = safe_exec('feedback = [r["id"] for r in data]', {"data": data})
        assert result["status"] == "ok"
        assert result["feedback"] == [1, 2, 3]

    def test_must_assign_feedback(self):
        result = safe_exec("x = 42")
        assert result["status"] == "error"
        assert "feedback" in result["error"]

    def test_empty_code(self):
        result = safe_exec("")
        assert result["status"] == "error"
        assert "Empty" in result["error"]

    def test_import_blocked(self):
        result = safe_exec("import os\nfeedback = 1")
        assert result["status"] == "error"
        assert "Blocked" in result["error"]

    def test_dunder_import_blocked(self):
        result = safe_exec('feedback = __import__("os")')
        assert result["status"] == "error"
        assert "Blocked" in result["error"]

    def test_syntax_error(self):
        result = safe_exec("feedback = [")
        assert result["status"] == "error"
        assert "SyntaxError" in result["error"]

    def test_type_classification_list(self):
        result = safe_exec("feedback = [1, 2, 3]")
        assert result["type"] == "list"

    def test_stdout_capture(self):
        result = safe_exec('print("hello")\nfeedback = 1')
        assert result["status"] == "ok"
        assert result["stdout"] == "hello\n"
        assert result["feedback"] == 1

    def test_stdout_on_error(self):
        result = safe_exec('print("before")\nfeedback = 1 / 0')
        assert result["status"] == "error"
        assert "before" in result["stdout"]

    def test_builtins_available(self):
        result = safe_exec("feedback = len([1, 2, 3])")
        assert result["feedback"] == 3

        result = safe_exec("feedback = max(1, 5, 3)")
        assert result["feedback"] == 5

        result = safe_exec("feedback = list(range(3))")
        assert result["feedback"] == [0, 1, 2]

    def test_no_variables(self):
        result = safe_exec("feedback = sum(range(10))")
        assert result["status"] == "ok"
        assert result["feedback"] == 45

    def test_cached_variables_in_scope(self):
        result = safe_exec(
            "feedback = len(data1) + len(data2)",
            {"data1": [1, 2, 3], "data2": [4, 5]},
        )
        assert result["status"] == "ok"
        assert result["feedback"] == 5

    def test_user_vars_returned_on_success(self):
        result = safe_exec("x = 42\ny = [1, 2]\nfeedback = 'done'")
        assert result["status"] == "ok"
        assert result["user_vars"] == {"x": 42, "y": [1, 2]}

    def test_user_vars_excludes_feedback(self):
        result = safe_exec("feedback = 'hi'")
        assert "feedback" not in result["user_vars"]

    def test_user_vars_excludes_injected(self):
        result = safe_exec("z = 99\nfeedback = data", {"data": [1]})
        assert result["user_vars"] == {"z": 99}
        assert "data" not in result["user_vars"]


# -- SandboxRunner --


class TestSandboxRunner:
    def test_tool_schema_shows_user_vars(self):
        ws = Workspace()
        ws.update_vars({"results": [{"sid": 1, "name": "GFP"}]})
        runner = SandboxRunner(ws)
        schema = runner.tool_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "python"
        assert "results" in schema["function"]["description"]
        assert "sid" in schema["function"]["description"]

    async def test_execute_with_user_vars(self):
        ws = Workspace()
        ws.update_vars({"data": [{"id": 1}, {"id": 2}, {"id": 3}]})
        runner = SandboxRunner(ws)
        result = await runner.execute('feedback = [r["id"] for r in data]')
        assert result["status"] == "ok"
        assert result["feedback"] == [1, 2, 3]

    def test_summary_for_llm_ok(self):
        ws = Workspace()
        runner = SandboxRunner(ws)
        result = {"status": "ok", "feedback": [1, 2, 3], "stdout": "", "type": "list"}
        summary = runner.summary_for_llm(result)
        assert "feedback = " in summary
        assert "[1, 2, 3]" in summary

    def test_summary_for_llm_error(self):
        ws = Workspace()
        runner = SandboxRunner(ws)
        result = {"status": "error", "error": "NameError: x", "stdout": ""}
        summary = runner.summary_for_llm(result)
        assert "Error:" in summary
        assert "NameError" in summary

    def test_summary_for_llm_with_stdout(self):
        ws = Workspace()
        runner = SandboxRunner(ws)
        result = {"status": "ok", "feedback": 42, "stdout": "debug\n", "type": "scalar"}
        summary = runner.summary_for_llm(result)
        assert "feedback = 42" in summary
        assert "stdout: debug" in summary

    def test_summary_for_llm_truncates(self):
        ws = Workspace()
        runner = SandboxRunner(ws, output_limit=40)
        big_list = list(range(1000))
        result = {"status": "ok", "feedback": big_list, "stdout": "", "type": "list"}
        summary = runner.summary_for_llm(result)
        assert len(summary) <= 40 + 50  # some overhead for "feedback = " prefix

    def test_tool_schema_empty_workspace(self):
        ws = Workspace()
        runner = SandboxRunner(ws)
        schema = runner.tool_schema()
        assert schema["function"]["name"] == "python"
        desc = schema["function"]["description"]
        assert "desc(var)" in desc

    async def test_report_dict_persists_across_calls(self):
        ws = Workspace()
        ws.update_vars({"data": [{"x": 1}, {"x": 2}]})
        runner = SandboxRunner(ws)
        result1 = await runner.execute('report["items"] = data\nfeedback = "stored items"')
        assert result1["status"] == "ok"
        assert runner.report == {"items": [{"x": 1}, {"x": 2}]}

        result2 = await runner.execute('report["count"] = len(data)\nfeedback = "stored count"')
        assert result2["status"] == "ok"
        assert runner.report == {"items": [{"x": 1}, {"x": 2}], "count": 2}

    async def test_report_dict_injected_into_namespace(self):
        ws = Workspace()
        ws.update_vars({"data": [1, 2, 3]})
        runner = SandboxRunner(ws)
        await runner.execute('report["step1"] = "done"\nfeedback = "ok"')
        result = await runner.execute('feedback = report.get("step1", "missing")')
        assert result["status"] == "ok"
        assert result["feedback"] == "done"

    async def test_user_vars_persist_across_calls(self):
        ws = Workspace()
        runner = SandboxRunner(ws)
        r1 = await runner.execute("filtered = [1, 2, 3]\nfeedback = 'stored'")
        assert r1["status"] == "ok"
        r2 = await runner.execute("feedback = len(filtered)")
        assert r2["status"] == "ok"
        assert r2["feedback"] == 3

    async def test_user_vars_shown_in_schema(self):
        ws = Workspace()
        runner = SandboxRunner(ws)
        await runner.execute("my_data = [1, 2]\nfeedback = 'ok'")
        schema = runner.tool_schema()
        desc = schema["function"]["description"]
        assert "my_data" in desc


class TestToolCallables:
    """Tests for sandbox-callable tools."""

    async def test_tool_signatures_in_schema(self):
        from hive.tools.base import Tool, ToolRegistry

        class GcTool(Tool):
            name = "gc"
            description = ("GC content", "Calculate GC content")
            tags = {"analysis"}
            params = {"sequence": {"type": "string", "description": "DNA sequence"}}

            def __init__(self, **_):
                pass

            async def execute(self, params):
                return {"gc_percent": 50.0}

        reg = ToolRegistry()
        reg.register(GcTool())

        ws = Workspace()
        runner = SandboxRunner(ws, registry=reg)
        schema = runner.tool_schema()
        desc = schema["function"]["description"]
        assert "gc(" in desc
        assert "sequence:string" in desc
        assert "-- GC content" in desc
        assert "desc(var) -- inspect" in desc

    async def test_callable_from_sandbox(self):
        from hive.tools.base import Tool, ToolRegistry

        class GcTool(Tool):
            name = "gc"
            description = ("GC content", "Calculate GC content")
            tags = {"analysis"}
            params = {"sequence": {"type": "string", "description": "DNA"}}

            def __init__(self, **_):
                pass

            async def execute(self, params):
                seq = params.get("sequence", "")
                gc = sum(1 for c in seq if c in "GC") / max(len(seq), 1) * 100
                return {"gc_percent": gc}

        reg = ToolRegistry()
        reg.register(GcTool())

        ws = Workspace()
        runner = SandboxRunner(ws, registry=reg)
        result = await runner.execute('r = gc(sequence="ATGC")\nfeedback = r["gc_percent"]')
        assert result["status"] == "ok"
        assert result["feedback"] == 50.0

    async def test_tool_call_budget_exceeded(self):
        from hive.tools.base import Tool, ToolRegistry

        class GcTool(Tool):
            name = "gc"
            description = ("GC content", "Calculate GC content")
            tags = {"analysis"}
            params = {"sequence": {"type": "string", "description": "DNA"}}

            def __init__(self, **_):
                pass

            async def execute(self, params):
                return {"gc_percent": 50.0}

        reg = ToolRegistry()
        reg.register(GcTool())

        ws = Workspace()
        runner = SandboxRunner(ws, registry=reg, tool_call_budget=2)
        result = await runner.execute(
            'results = [gc(sequence="ATGC") for _ in range(3)]\nfeedback = len(results)'
        )
        assert result["status"] == "error"
        assert "budget exceeded" in result["error"]


class TestDescBuiltin:
    """Tests for desc() sandbox builtin."""

    async def test_desc_in_sandbox(self):
        ws = Workspace()
        ws.update_vars({"results": [{"sid": 1, "name": "GFP"}]})
        runner = SandboxRunner(ws)
        result = await runner.execute('feedback = desc(results, name="results")')
        assert result["status"] == "ok"
        assert "sid" in result["feedback"]
        assert len(ws._desc_results) == 1
        assert ws._desc_results[0][0] == "results"

    async def test_desc_shown_in_describe(self):
        ws = Workspace()
        ws.add_desc_result("myvar", "2 rows -- {sid: int, name: str}")
        desc = ws.describe()
        assert "desc(myvar):" in desc
        assert "2 rows" in desc
