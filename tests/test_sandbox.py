"""Tests for sandbox: Workspace, safe_exec, and SandboxRunner."""

from hive.sandbox.exec import safe_exec
from hive.sandbox.runner import SandboxRunner
from hive.sandbox.workspace import Workspace

# ── Workspace ──


class TestWorkspace:
    def test_store_and_get(self):
        ws = Workspace()
        rows = [{"id": 1, "name": "GFP"}]
        handle = ws.store("results", rows, "search", {"query": "GFP"})
        assert handle == "p0"
        assert ws.get("p0") == rows

    def test_sequential_handles(self):
        ws = Workspace()
        h0 = ws.store("results", [{"a": 1}], "search")
        h1 = ws.store("hits", [{"b": 2}], "blast")
        h2 = ws.store("parts", [{"c": 3}], "parts")
        assert (h0, h1, h2) == ("p0", "p1", "p2")

    def test_get_missing(self):
        ws = Workspace()
        assert ws.get("p0") is None
        assert ws.get("r99") is None
        assert ws.get("invalid") is None

    def test_describe_list_dict(self):
        ws = Workspace()
        ws.store("results", [{"sid": 1, "name": "GFP", "size": 720}], "search", {"query": "GFP"})
        desc = ws.describe()
        assert "# p0" in desc
        assert "1 rows" in desc
        assert "sid" in desc
        # Example row shown on next line
        assert "p0[0]" in desc

    def test_describe_string(self):
        ws = Workspace()
        ws.store("sequence_data", "ATGC" * 100, "profile")
        desc = ws.describe()
        assert "str(400)" in desc

    def test_describe_list_int(self):
        ws = Workspace()
        ws.store("fragments", [4521, 2100, 800], "digest")
        desc = ws.describe()
        assert "list(3)" in desc

    def test_describe_dict(self):
        ws = Workspace()
        ws.store("gel_data", {"lanes": [], "gelType": "agarose", "stain": "ethidium"}, "digest")
        desc = ws.describe()
        assert "dict" in desc
        assert "gelType" in desc

    def test_describe_scope(self):
        ws = Workspace()
        ws.store("results", [{"a": 1}], "search")
        ws.store("sequence_data", "ATGC" * 100, "profile")
        text = ws.describe()
        assert "# p0" in text
        assert "# p1" in text

    def test_namespace(self):
        ws = Workspace()
        rows0 = [{"x": 1}]
        seq = "ATGCATGC"
        ws.store("results", rows0, "search")
        ws.store("sequence_data", seq, "profile")
        ns = ws.namespace()
        assert ns["p0"] is rows0
        assert ns["p1"] is seq
        assert len(ns) == 2

    def test_find_by_field(self):
        ws = Workspace()
        ws.store("sequence_data", "ATGC" * 100, "profile")
        ws.store("results", [{"a": 1}], "search")
        # Should find the string by field name
        found = ws.find_by_field("sequence_data", min_length=10)
        assert found == "ATGC" * 100

    def test_find_by_field_min_length(self):
        ws = Workspace()
        ws.store("sequence_data", "ATG", "profile")
        # Too short
        assert ws.find_by_field("sequence_data", min_length=100) is None
        # No min_length requirement
        assert ws.find_by_field("sequence_data") == "ATG"

    def test_find_by_field_most_recent(self):
        ws = Workspace()
        ws.store("sequence_data", "FIRST", "profile")
        ws.store("sequence_data", "SECOND", "profile")
        assert ws.find_by_field("sequence_data") == "SECOND"

    def test_find_by_field_skips_non_strings(self):
        ws = Workspace()
        ws.store("sequence", {"sid": 1, "name": "GFP"}, "search")
        # Dict with matching field name should NOT be returned
        assert ws.find_by_field("sequence") is None
        # But a string with the same field name should be found
        ws.store("sequence", "ATGCATGC", "profile")
        assert ws.find_by_field("sequence") == "ATGCATGC"

    def test_find_by_field_not_found(self):
        ws = Workspace()
        ws.store("results", [{"a": 1}], "search")
        assert ws.find_by_field("sequence_data") is None

    def test_column_names_capped(self):
        """Columns beyond max_cols show '...' in describe."""
        ws = Workspace()
        row = {f"col{i}": i for i in range(12)}
        ws.store("results", [row], "wide_tool")
        desc = ws.describe()
        assert "..." in desc


# ── safe_exec ──


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
        """Core builtins (len, sum, min, max, etc.) work."""
        result = safe_exec("feedback = len([1, 2, 3])")
        assert result["feedback"] == 3

        result = safe_exec("feedback = max(1, 5, 3)")
        assert result["feedback"] == 5

        result = safe_exec("feedback = list(range(3))")
        assert result["feedback"] == [0, 1, 2]

    def test_no_variables(self):
        """Code can run without any injected variables."""
        result = safe_exec("feedback = sum(range(10))")
        assert result["status"] == "ok"
        assert result["feedback"] == 45

    def test_cached_variables_in_scope(self):
        """Variables from workspace namespace are accessible."""
        result = safe_exec(
            "feedback = len(r0) + len(r1)",
            {"r0": [1, 2, 3], "r1": [4, 5]},
        )
        assert result["status"] == "ok"
        assert result["feedback"] == 5

    def test_user_vars_returned_on_success(self):
        """New variables created in code are returned in user_vars."""
        result = safe_exec("x = 42\ny = [1, 2]\nfeedback = 'done'")
        assert result["status"] == "ok"
        assert result["user_vars"] == {"x": 42, "y": [1, 2]}

    def test_user_vars_excludes_feedback(self):
        """feedback is not included in user_vars."""
        result = safe_exec("feedback = 'hi'")
        assert "feedback" not in result["user_vars"]

    def test_user_vars_excludes_injected(self):
        """Injected variables are not re-captured in user_vars."""
        result = safe_exec("z = 99\nfeedback = data", {"data": [1]})
        assert result["user_vars"] == {"z": 99}
        assert "data" not in result["user_vars"]


# ── SandboxRunner ──


class TestSandboxRunner:
    def test_tool_schema_includes_workspace(self):
        ws = Workspace()
        ws.store("results", [{"sid": 1, "name": "GFP"}], "search")
        runner = SandboxRunner(ws)
        schema = runner.tool_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "python"
        assert "# p0" in schema["function"]["description"]
        assert "sid" in schema["function"]["description"]

    async def test_execute_dispatches(self):
        ws = Workspace()
        data = [{"id": 1}, {"id": 2}, {"id": 3}]
        ws.store("results", data, "search")
        runner = SandboxRunner(ws)
        result = await runner.execute('feedback = [r["id"] for r in p0]')
        assert result["status"] == "ok"
        assert result["feedback"] == [1, 2, 3]

    async def test_execute_with_string_handle(self):
        ws = Workspace()
        ws.store("sequence_data", "ATGCATGC", "profile")
        runner = SandboxRunner(ws)
        result = await runner.execute("feedback = len(p0)")
        assert result["status"] == "ok"
        assert result["feedback"] == 8

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
        # Empty workspace still shows available commands
        desc = schema["function"]["description"]
        assert "desc(var)" in desc

    async def test_report_dict_persists_across_calls(self):
        """Report dict accumulates data across multiple sandbox calls."""
        ws = Workspace()
        ws.store("data", [{"x": 1}, {"x": 2}], "search")
        runner = SandboxRunner(ws)
        result1 = await runner.execute('report["items"] = p0\nfeedback = "stored items"')
        assert result1["status"] == "ok"
        assert runner.report == {"items": [{"x": 1}, {"x": 2}]}

        result2 = await runner.execute('report["count"] = len(p0)\nfeedback = "stored count"')
        assert result2["status"] == "ok"
        assert runner.report == {"items": [{"x": 1}, {"x": 2}], "count": 2}

    async def test_report_dict_injected_into_namespace(self):
        """Report dict is accessible in sandbox code."""
        ws = Workspace()
        ws.store("data", [1, 2, 3], "tool")
        runner = SandboxRunner(ws)
        await runner.execute('report["step1"] = "done"\nfeedback = "ok"')
        result = await runner.execute('feedback = report.get("step1", "missing")')
        assert result["status"] == "ok"
        assert result["feedback"] == "done"

    async def test_user_vars_persist_across_calls(self):
        """Variables from call 1 are accessible in call 2."""
        ws = Workspace()
        runner = SandboxRunner(ws)
        r1 = await runner.execute("filtered = [1, 2, 3]\nfeedback = 'stored'")
        assert r1["status"] == "ok"
        r2 = await runner.execute("feedback = len(filtered)")
        assert r2["status"] == "ok"
        assert r2["feedback"] == 3

    async def test_user_vars_shown_in_schema(self):
        """tool_schema description includes persisted variable names."""
        ws = Workspace()
        runner = SandboxRunner(ws)
        await runner.execute("my_data = [1, 2]\nfeedback = 'ok'")
        schema = runner.tool_schema()
        desc = schema["function"]["description"]
        assert "my_data" in desc

    async def test_user_vars_dont_override_workspace(self):
        """Workspace handles take precedence over user vars with same name."""
        ws = Workspace()
        ws.store("results", [{"a": 1}], "search")
        runner = SandboxRunner(ws)
        # Create user var named p0
        await runner.execute("p0 = 'overwritten'\nfeedback = 'ok'")
        # Workspace namespace is applied after _user_vars, so p0 = workspace data
        result = await runner.execute("feedback = len(p0)")
        assert result["status"] == "ok"
        assert result["feedback"] == 1  # workspace [{"a": 1}], not string


class TestToolCallables:
    """Tests for sandbox-callable tools."""

    async def test_tool_signatures_in_schema(self):
        """Tool signatures appear in python schema description."""
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
        """Tools can be called as functions inside sandbox code."""
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
        """Exceeding tool call budget raises RuntimeError."""
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

    async def test_tool_results_auto_stored_with_provenance(self):
        """Tool calls from sandbox auto-store results with call_repr."""
        from hive.tools.base import Tool, ToolRegistry

        class GcTool(Tool):
            name = "gc"
            description = ("GC content", "Calculate GC content")
            tags = {"analysis"}
            params = {"sequence": {"type": "string", "description": "DNA"}}

            def __init__(self, **_):
                pass

            async def execute(self, params):
                return {"gc_percent": 50.0, "length": 4}

        reg = ToolRegistry()
        reg.register(GcTool())

        ws = Workspace()
        runner = SandboxRunner(ws, registry=reg)
        result = await runner.execute('r = gc(sequence="ATGC")\nfeedback = r["gc_percent"]')
        assert result["status"] == "ok"
        assert result["feedback"] == 50.0
        # Tool calls now auto-store with provenance
        assert len(ws) >= 1
        entry = ws._entries[0]
        assert 'gc(sequence="ATGC")' in entry.call_repr


class TestDescribeFormat:
    """Tests for the new Python-comment style describe() format."""

    def test_call_repr_shown(self):
        ws = Workspace()
        ws.store("results", [{"sid": 1}], "search", call_repr='search(query="GFP")')
        desc = ws.describe()
        assert '# p0 = search(query="GFP") -> 1 rows' in desc

    def test_example_row_for_list_dict(self):
        ws = Workspace()
        ws.store("results", [{"sid": 42, "name": "pET-28a"}], "search")
        desc = ws.describe()
        assert "p0[0]" in desc
        assert "sid: 42" in desc
        assert "name: 'pET-28a'" in desc

    def test_no_example_row_for_scalar(self):
        ws = Workspace()
        ws.store("count", 42, "tool")
        desc = ws.describe()
        assert "[0]" not in desc

    def test_user_vars_shown(self):
        ws = Workspace()
        ws.update_vars({"filtered": [1, 2, 3]})
        desc = ws.describe()
        assert "# filtered" in desc

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


class TestHistoryFormat:
    """Tests for the new ok/x prefixed history() format."""

    def test_ok_with_produced(self):
        ws = Workspace()
        ws.add_step("python", "done", produced="p0 (56 rows)")
        h = ws.history()
        assert "# ok: python -> p0 (56 rows)" in h

    def test_ok_without_produced(self):
        ws = Workspace()
        ws.add_step("python", "filtered 3 items", code="x = 1")
        h = ws.history()
        assert "# ok: python -> filtered 3 items" in h

    def test_error_with_hint(self):
        ws = Workspace()
        ws.add_step("python", "err", error="KeyError: 'gc'", hint="keys: {sid, name}")
        h = ws.history()
        assert "# x: python KeyError: 'gc' -- keys: {sid, name}" in h

    def test_error_without_hint(self):
        ws = Workspace()
        ws.add_step("python", "err", error="ZeroDivisionError")
        h = ws.history()
        assert "# x: python ZeroDivisionError" in h
        assert "--" not in h

    def test_max_steps(self):
        ws = Workspace()
        for i in range(8):
            ws.add_step("python", f"step {i}")
        h = ws.history(max_steps=3)
        assert "earlier steps omitted" in h
        assert h.count("# ok:") == 3


class TestDescBuiltin:
    """Tests for desc() sandbox builtin."""

    async def test_desc_in_sandbox(self):
        ws = Workspace()
        ws.store("results", [{"sid": 1, "name": "GFP"}], "search")
        runner = SandboxRunner(ws)
        result = await runner.execute('feedback = desc(p0, name="p0")')
        assert result["status"] == "ok"
        assert "sid" in result["feedback"]
        # desc result recorded in workspace
        assert len(ws._desc_results) == 1
        assert ws._desc_results[0][0] == "p0"

    async def test_desc_shown_in_describe(self):
        ws = Workspace()
        ws.add_desc_result("p0", "2 rows -- {sid: int, name: str}")
        desc = ws.describe()
        assert "desc(p0):" in desc
        assert "2 rows" in desc


class TestStoreResult:
    """Tests for Workspace.store_result()."""

    def test_single_handle(self):
        """store_result creates exactly one handle."""
        ws = Workspace()
        data = {"results": [{"x": 1}], "count": 1}
        handle = ws.store_result(data, "tool")
        assert handle == "p0"
        assert len(ws) == 1
        assert ws.get("p0") is data

    def test_call_repr_stored(self):
        ws = Workspace()
        ws.store_result({"a": 1}, "search", call_repr='search(query="x")')
        entry = ws._entries[0]
        assert entry.call_repr == 'search(query="x")'

    def test_describe_shows_all_handles(self):
        """describe() shows all pipeline handles."""
        ws = Workspace()
        ws.store("results", [{"a": 1}], "search")
        ws.store("sequence", "ATGC" * 100, "profile")
        desc = ws.describe()
        assert "# p0" in desc
        assert "# p1" in desc

